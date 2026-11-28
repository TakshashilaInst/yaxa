"""HTTP API for Yaxa Learn, mounted at /api/yaxa (see scripts/yaxa/overlay.py).

Auth: every route already passed DeepTutor's ``require_auth``; this module adds
Yaxa's own access rules (enrolment decides which modules a student can use).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from deeptutor.multi_user.context import get_current_user

from . import (
    announcements,
    checks,
    cohort,
    discussion,
    grounding,
    library_api,
    module_page,
    panel,
    practice,
    prompting,
    schedule,
    store,
    whats_new,
)
from . import chat as cohort_chat  # cohort chat; `chat` below is the Yaxa tutor route
from .access import (  # noqa: F401  (_cited_numbers is re-exported for tests)
    _allowed_modules,
    _cited_numbers,
    _faculty,
    _me,
    _privileged,
    _public_passage,
    _require_module,
    _short,
    _sse,
    programme_kbs,
)
from .catalog import Catalog, get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for, stream_text
from .sim import api as sim_api

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(practice.router)
router.include_router(checks.admin_router)
router.include_router(checks.router)
router.include_router(whats_new.router)
router.include_router(cohort.router)
router.include_router(panel.router)
router.include_router(module_page.router)
router.include_router(schedule.router)
router.include_router(announcements.router)
router.include_router(discussion.router)
router.include_router(cohort_chat.router)
router.include_router(library_api.router)
router.include_router(sim_api.router)

HISTORY_TURNS = 10  # earlier turns sent back to the model for context
DEMO_RETURN_COOKIE = "yaxa_demo_return"


# ------------------------------------------------------------------ helpers
def _programme_view(cat: Catalog, prog, track_code: str | None = None) -> dict[str, Any]:
    def mod(code: str) -> dict[str, Any]:
        m = cat.module(code)
        return {
            "code": code,
            "title": m.title if m else code,
            "available": bool(m and m.available),
            "units": [u.model_dump() for u in (m.units if m else [])],
        }

    return {
        "code": prog.code,
        "name": prog.name,
        "summary": prog.summary,
        "tracks": [
            {
                "code": t.code,
                "name": t.name,
                "core": [mod(c) for c in t.core],
                "specialisation": [mod(c) for c in t.specialisation],
            }
            for t in prog.tracks
        ],
        "modules": [mod(c) for c in prog.modules],
    }


# --------------------------------------------------------------- basic routes
@router.get("/health")
async def health() -> dict[str, Any]:
    cat = get_catalog()
    return {"ok": True, "programmes": len(cat.programmes), "modules": len(cat.modules)}


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    enrolled = []
    for e in user.enrolments:
        prog = cat.programme(e.programme)
        if prog:
            view = _programme_view(cat, prog)
            view["track"] = e.track
            view["cohort"] = e.cohort
            enrolled.append(view)
    return {
        "user_id": cu.id,
        "username": cu.username,
        "display_name": user.display_name or cu.username,
        "is_admin": bool(cu.is_admin),
        "role": user.role,
        "demo": user.demo,
        "avatar": user.avatar,
        "in_demo_session": bool(request.cookies.get(DEMO_RETURN_COOKIE)),
        "onboarded": user.onboarded,
        "profile": user.profile,
        "profile_fields": store.PROFILE_FIELDS,
        "enrolments": enrolled,
        "allowed_modules": _allowed_modules(cat, cu, user),
        "model_mode": cat.settings.model_mode,
    }


class ProfileBody(BaseModel):
    profile: dict[str, str]
    display_name: str | None = None


@router.put("/me/profile")
async def put_profile(body: ProfileBody) -> dict[str, Any]:
    _, user = _me()
    user.profile = store.clean_profile(body.profile)
    if body.display_name:
        user.display_name = body.display_name.strip()[:80]
    store.save_user(user)
    return {"ok": True, "profile": user.profile}


class EnrolBody(BaseModel):
    programme: str
    track: str | None = None
    cohort: str | None = None


@router.post("/me/enrolments")
async def enrol(body: EnrolBody) -> dict[str, Any]:
    """Self-enrolment, allowed while Yaxa is a demo (allow_self_enrol in config)."""
    cu, user = _me()
    cat = get_catalog()
    if not (cu.is_admin or cat.settings.allow_self_enrol):
        raise HTTPException(403, "Ask Takshashila to enrol you")
    prog = cat.programme(body.programme)
    if not prog:
        raise HTTPException(404, "Unknown programme")
    if prog.tracks and not prog.track(body.track):
        raise HTTPException(400, f"{prog.code} needs a track: {', '.join(t.code for t in prog.tracks)}")
    user.enrolments = [e for e in user.enrolments if e.programme != prog.code]
    user.enrolments.append(store.Enrolment(programme=prog.code, track=body.track, cohort=body.cohort))
    store.save_user(user)
    return {"ok": True}


@router.delete("/me/enrolments/{programme}")
async def unenrol(programme: str) -> dict[str, Any]:
    cu, user = _me()
    if not (cu.is_admin or get_catalog().settings.allow_self_enrol):
        raise HTTPException(403, "Ask Takshashila to change your enrolment")
    user.enrolments = [e for e in user.enrolments if e.programme != programme]
    store.save_user(user)
    return {"ok": True}


@router.get("/catalog")
async def catalog() -> dict[str, Any]:
    cat = get_catalog()
    return {"programmes": [_programme_view(cat, p) for p in cat.programmes]}


@router.get("/faculty")
async def faculty() -> list[dict[str, Any]]:
    return [
        {"slug": f.slug, "name": f.name, "title": f.title, "label": f.label, "ready": bool(f.kb)}
        for f in get_catalog().faculty.values()
    ]


@router.get("/conversations")
async def conversations() -> list[dict[str, Any]]:
    cu, _ = _me()
    return store.list_conversations(cu.id)


@router.get("/conversations/{conv_id}")
async def conversation(conv_id: str) -> dict[str, Any]:
    cu, _ = _me()
    conv = store.load_conversation(cu.id, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv.model_dump()


# --------------------------------------------------------- starters & topics
@router.get("/starters")
async def starters(module: str, unit: str | None = None) -> list[str]:
    """Personalised opening questions. Built from templates: no model call."""
    cu, user = _me()
    cat = get_catalog()
    mod = _require_module(cat, cu, user, module)
    assert mod is not None
    field = user.profile.get("field") or "my field"
    work = user.profile.get("researching") or user.profile.get("immediate_goal") or ""
    chosen = mod.unit(unit)
    units = [chosen] if chosen else mod.units[:3]
    out = []
    if units:
        out.append(f"Explain the main idea of “{units[0].title}” with an example from {field.lower()}.")
    if len(units) > 1:
        out.append(f"What is the most common mistake people make when thinking about “{units[1].title}”?")
    if work:
        topic = units[0].title if units else mod.title
        out.append(f"How would “{topic}” change how I approach this: {_short(work)}")
    elif len(units) > 2:
        out.append(f"Give me a real Indian case that shows “{units[2].title}” in action.")
    return out


@router.get("/socratic/topics")
async def socratic_topics(module: str, unit: str | None = None, conversation_id: str | None = None) -> list[str]:
    cu, user = _me()
    cat = get_catalog()
    mod = _require_module(cat, cu, user, module)
    assert mod is not None
    topics: list[str] = []
    if conversation_id:
        conv = store.load_conversation(cu.id, conversation_id)
        if conv and conv.title:
            topics.append(f"Continue: {conv.title}")
    chosen = mod.unit(unit)
    units = [chosen] if chosen else mod.units[:3]
    topics += [u.title for u in units]
    work = user.profile.get("researching")
    if work and units:
        topics.append(f"{units[0].title}, applied to: {_short(work, 120)}")
    return topics


# ---------------------------------------------------------------- the chat
class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
    module: str | None = None
    unit: str | None = None
    faculty: str | None = None
    socratic: bool = False
    scope: Literal["module", "programme"] = "module"  # programme: search every library the student can use


@router.post("/chat")
async def chat(body: ChatBody) -> StreamingResponse:
    cu, user = _me()
    cat = get_catalog()
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Empty message")
    if len(message) > 6000:
        raise HTTPException(413, "Message too long")

    conv = store.load_conversation(cu.id, body.conversation_id) if body.conversation_id else None
    if body.conversation_id and not conv:
        raise HTTPException(404, "Conversation not found")
    across = (conv.kind == "programme") if conv else body.scope == "programme"
    module = None if across else _require_module(cat, cu, user, body.module or (conv.module if conv else None))
    unit = module.unit(body.unit or (conv.unit if conv else None)) if module else None
    fac = _faculty(cat, body.faculty)
    programme_modules = [m for c in _allowed_modules(cat, cu, user) if (m := cat.module(c)) and m.available] if across else []

    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, cat.settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's question limit. It resets tomorrow.")

    if not conv:
        conv = store.Conversation(
            user_id=cu.id,
            kind="programme" if across else "chat",
            module=module.code if module else None,
            unit=unit.id if unit else None,
            title=_short(message, 70),
        )

    async def events():
        # 1) retrieve from the module KB (+ the faculty member's own KB)
        yield _sse("meta", {"conversation_id": conv.id, "faculty_label": fac.label if fac else None})
        query = message
        if body.socratic and conv.turns:
            # short answers ("yes", "the cost?") retrieve poorly; add the topic
            query = f"{conv.title}. {message}"
        k = cat.settings.retrieval_top_k
        jobs = []
        if across:
            jobs.append(grounding.retrieve_across(programme_kbs(cat, cu, user), query, k))
        elif module and module.kb:
            jobs.append(grounding.retrieve(module.kb, query, k, corpus=module.title))
        if fac and fac.kb and not across:  # across already searches the faculty libraries
            jobs.append(grounding.retrieve(fac.kb, query, max(3, k // 2), corpus=f"{fac.name}'s work"))
        results = await asyncio.gather(*jobs) if jobs else []
        passages = [p for group in results for p in group]
        yield _sse("sources", [_public_passage(p, i) for i, p in enumerate(passages, 1)])

        # 2) prompt: system + recent history + this question with its passages
        system = prompting.build_system(
            profile=user.profile,
            learner_name=user.display_name,
            module=module,
            unit=unit,
            faculty=fac,
            socratic=body.socratic,
            programme_modules=programme_modules,
        )
        history = [
            {"role": t.role, "content": t.content}
            for t in conv.turns[-HISTORY_TURNS:]
            if t.role in ("user", "assistant")
        ]
        user_turn = (
            f"{message}\n\n---\nCourse passages for this turn:\n\n"
            f"{prompting.number_passages(passages, fac)}"
        )
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_turn}]

        # 3) stream the answer
        answer = ""
        try:
            async for chunk in stream_text(config, messages):
                answer += chunk
                yield _sse("delta", chunk)
        except Exception as exc:  # provider down, bad key, etc.
            logger.exception("yaxa chat stream failed")
            yield _sse("error", f"Yaxa couldn't reach its model: {type(exc).__name__}")
            return

        # 4) citations: which numbers were used, and which don't exist
        cited = _cited_numbers(answer)
        citations = [{"n": n, "dangling": not (1 <= n <= len(passages))} for n in cited]
        yield _sse("citations", citations)
        cited_files = {passages[n - 1]["file"] for n in cited if 1 <= n <= len(passages)}
        worth, seen_files = [], set(cited_files)
        for i, p in enumerate(passages, 1):
            course_kb = (p["kb"] in {m.kb for m in programme_modules}) if across else p["kb"] == (module.kb if module else None)
            if p["file"] not in seen_files and course_kb:
                worth.append(_public_passage(p, i))
                seen_files.add(p["file"])
            if len(worth) == 2:
                break
        yield _sse("worth_reading", worth)

        # 5) save the turn
        conv.turns.append(store.Turn(role="user", content=message, socratic=body.socratic, faculty=body.faculty))
        conv.turns.append(
            store.Turn(
                role="assistant",
                content=answer,
                socratic=body.socratic,
                faculty=body.faculty,
                sources=[_public_passage(p, i) for i, p in enumerate(passages, 1)],
                citations=citations,
            )
        )
        store.save_conversation(conv)
        yield _sse("done", {"conversation_id": conv.id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------- export
class ExportBody(BaseModel):
    conversation_id: str


EXPORT_PROMPT = """\
Turn this tutoring conversation into study notes the student can keep. Markdown.
Structure:
# <short title>
## Key ideas  (each idea in 2-3 sentences, in plain words, with the student's own examples where they gave them)
## How I'd apply this  (to the student's own work, from what they said)
## Questions I'm still thinking about
## Sources  (the readings cited, by title and page)
Write in the second person ("you"). Don't invent content that isn't in the conversation."""


@router.post("/export")
async def export_notes(body: ExportBody) -> Response:
    cu, user = _me()
    conv = store.load_conversation(cu.id, body.conversation_id)
    if not conv or not conv.turns:
        raise HTTPException(404, "Nothing to export yet")
    sources: dict[tuple[str, Any], None] = {}
    for t in conv.turns:
        for s in t.sources:
            for c in t.citations:
                if c["n"] == s.get("n") and not c["dangling"]:
                    sources[(s["title"], s.get("page"))] = None
    transcript = "\n\n".join(f"{t.role.upper()}: {t.content}" for t in conv.turns)
    cited = "\n".join(f"- {t}" + (f", p. {p}" if p else "") for t, p in sources) or "(none)"
    try:
        config = resolve_for(cu.id)
        notes = await complete_text(
            config,
            [
                {"role": "system", "content": EXPORT_PROMPT},
                {"role": "user", "content": f"Readings cited:\n{cited}\n\nConversation:\n{transcript}"},
            ],
        )
    except Exception:
        logger.warning("yaxa export: model unavailable, exporting transcript", exc_info=True)
        notes = f"# {conv.title}\n\n" + transcript.replace("USER:", "**You:**").replace("ASSISTANT:", "**Yaxa:**")
    filename = re.sub(r"[^A-Za-z0-9]+", "-", conv.title).strip("-")[:50] or "yaxa-notes"
    return Response(
        notes,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
    )


# -------------------------------------------------------------------- files
@router.get("/files/{kb}/{file_name:path}")
async def kb_file(kb: str, file_name: str) -> FileResponse:
    cu, user = _me()
    cat = get_catalog()
    allowed_kbs = {cat.modules[c].kb for c in _allowed_modules(cat, cu, user) if c in cat.modules}
    allowed_kbs |= {f.kb for f in cat.faculty.values() if f.kb}
    if kb not in allowed_kbs:
        raise HTTPException(403, "Not available to you")
    path = grounding.kb_raw_path(kb, file_name)
    if not path:
        raise HTTPException(404, "File not found")
    try:
        store.mark_opened(cu.id, kb, file_name)
    except Exception:  # a tick is never worth blocking the reading
        logger.warning("yaxa: could not record an opened reading", exc_info=True)
    suffix = path.suffix.lower()
    # transcripts and notes open as readable text in the browser, not as a download
    media = "application/pdf" if suffix == ".pdf" else "text/plain; charset=utf-8" if suffix in {".md", ".txt"} else None
    return FileResponse(path, media_type=media, content_disposition_type="inline", filename=path.name)


# ---------------------------------------------------- demo: switch student
def _demo_admin(request: Request):
    """The admin behind this browser: logged in now, or parked in the demo cookie."""
    from deeptutor.services.auth import decode_token

    cu = get_current_user()
    if cu.is_admin:
        return cu
    parked = decode_token(request.cookies.get(DEMO_RETURN_COOKIE, ""))
    if parked and parked.role == "admin":
        return parked
    raise HTTPException(403, "Only an admin can use the demo gallery")


@router.get("/demo/students")
async def demo_students(request: Request) -> list[dict[str, Any]]:
    _demo_admin(request)
    return [
        {"user_id": u.user_id, "name": u.display_name, "profile": u.profile, "avatar": u.avatar}
        for u in store.list_users()
        if u.demo
    ]


@router.post("/demo/enter/{user_id}")
async def demo_enter(user_id: str, request: Request, response: Response) -> dict[str, Any]:
    """Sign this browser in as a seeded demo student; the admin session is parked."""
    from deeptutor.api.routers.auth import _COOKIE_MAX_AGE, _cookie_attrs
    from deeptutor.multi_user.audit import log_admin_action
    from deeptutor.services.auth import create_token

    admin = _demo_admin(request)
    target = store.load_user(user_id)
    if not target.demo:
        raise HTTPException(403, "Only seeded demo students can be entered")
    attrs = _cookie_attrs()
    if not request.cookies.get(DEMO_RETURN_COOKIE):
        admin_token = request.cookies.get(attrs["key"], "")
        response.set_cookie(**(attrs | {"key": DEMO_RETURN_COOKIE}), value=admin_token, max_age=_COOKIE_MAX_AGE)
    username = target.display_name
    from deeptutor.multi_user.identity import load_users

    for name, record in (load_users() or {}).items():
        if str(record.get("id")) == user_id:
            username = name
            break
    response.set_cookie(**attrs, value=create_token(username, "user", user_id), max_age=_COOKIE_MAX_AGE)
    try:
        log_admin_action("yaxa_demo_enter", target_user_id=user_id)
    except Exception:  # audit is best-effort; never block the demo on it
        logger.info("yaxa demo: audit log unavailable", exc_info=True)
    logger.info("yaxa demo: %s entered as %s", getattr(admin, "username", "admin"), username)
    return {"ok": True}


@router.post("/demo/exit")
async def demo_exit(request: Request, response: Response) -> dict[str, Any]:
    from deeptutor.api.routers.auth import _COOKIE_MAX_AGE, _cookie_attrs

    parked = request.cookies.get(DEMO_RETURN_COOKIE)
    if not parked:
        return {"ok": True}
    attrs = _cookie_attrs()
    response.set_cookie(**attrs, value=parked, max_age=_COOKIE_MAX_AGE)
    response.delete_cookie(**(attrs | {"key": DEMO_RETURN_COOKIE}))
    return {"ok": True}
