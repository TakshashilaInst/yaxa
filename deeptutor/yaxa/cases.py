"""Weekly case: one real Indian case per session that Yaxa teaches the session's idea through.

Yaxa drafts a case from the session's readings; faculty edit and approve it (as with session checks).
Learners see an approved case only, never its grasp notes: those tell Yaxa what a learner who has
understood the idea can say, and are used to guide the Learn session and judge explain-back.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import community, grounding, prompting, store
from .access import _me, _privileged, _require_module, _short, parse_json_reply
from .catalog import get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)

MIN_WORDS = 80
MAX_WORDS = 400
MIN_GRASP = 2
MAX_GRASP = 5
PASSAGES = 10
MIN_EXPLAIN_WORDS = 25
KEEP_ATTEMPTS = 5

router = APIRouter(prefix="/cases")
admin_router = APIRouter(prefix="/cases/admin")  # mounted before `router`, whose /{module}/{session} would match it


class Case(BaseModel):
    module: str
    session: str
    status: Literal["draft", "approved"] = "draft"
    version: int = 1
    title: str = ""
    situation: str = ""
    opening: str = ""  # Yaxa's first question in the Learn session
    grasp: list[str] = Field(default_factory=list)  # staff and model only
    approved_by: str = ""
    approved_at: str = ""


def validate(c: Case) -> list[str]:
    """Plain-language problems that stop a case being saved or approved; empty when fine."""
    problems = []
    if not c.title.strip():
        problems.append("Give the case a title.")
    elif len(c.title) > 120:
        problems.append("Keep the title under 120 characters.")
    n = len(c.situation.split())
    if not MIN_WORDS <= n <= MAX_WORDS:
        problems.append(f"The situation should be {MIN_WORDS}–{MAX_WORDS} words (it is {n}).")
    if not c.opening.strip():
        problems.append("Write the opening question Yaxa asks first.")
    notes = [g for g in c.grasp if g.strip()]
    if not MIN_GRASP <= len(notes) <= MAX_GRASP:
        problems.append(f"List {MIN_GRASP}–{MAX_GRASP} things a learner who understands the idea can say.")
    return problems


def _case_path(module: str, session: str):
    return community.root("cases", store._safe(module)) / f"{store._safe(session)}.json"


def load_case(module: str, session: str) -> Case | None:
    data = store._read_json(_case_path(module, session))
    return Case.model_validate(data) if data else None


def save_case(c: Case) -> None:
    store._write_json(_case_path(c.module, c.session), c.model_dump())


def public_view(c: Case) -> dict[str, Any]:
    """What a learner sees: never the grasp notes."""
    return {"module": c.module, "session": c.session, "version": c.version,
            "title": c.title, "situation": c.situation, "opening": c.opening}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ faculty: draft, edit, approve
DRAFT_PROMPT = """\
You write the weekly case for a Takshashila public policy course for working professionals. In the Learn
session, Yaxa teaches this session's idea THROUGH the case: the learner reasons about the case first, and the
idea emerges from their reasoning.
Choose one real Indian policy episode that cannot be understood well without this session's idea. Take it from
the numbered course passages or from a well-known public episode; faculty will check the facts. Prefer a
recent episode.
- "situation": 150-300 words, plain language, concrete actors, numbers where you know them, ending in a decision
  or a puzzle. Do not explain the idea itself.
- "opening": the first question Yaxa asks, under 40 words. It makes the learner reason before any explanation.
- "grasp": 2-5 short statements a learner who has understood the idea could make about this case.
Takshashila's usage: "State" means the political institution in Max Weber's sense (the body holding the
monopoly on the legitimate use of force over a territory), never an Indian sub-national state; say "state
government" for those. Plain text, no markdown.

Reply with JSON only, no other text:
{"title": "<under 80 characters>", "situation": "<text>", "opening": "<question>", "grasp": ["<statement>", ...]}"""


class EditBody(BaseModel):
    title: str
    situation: str
    opening: str
    grasp: list[str]


def _require_staff():
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Cases are edited by faculty")
    return cu, user


def _module_unit(module: str, session: str):
    mod = get_catalog().module(module)
    unit = next((u for u in mod.units if u.id == session), None) if mod else None
    if not mod or not unit:
        raise HTTPException(404, "No such session in this module")
    return mod, unit


def _staff_name(cu, user) -> str:
    name = (user.display_name or cu.id or "").strip()
    return name.split("@")[0] if "@" in name else name


def _parse_case(data: dict | None, module: str, session: str) -> Case | None:
    if not isinstance(data, dict):
        return None
    try:
        c = Case(module=module, session=session, title=str(data.get("title") or "").strip(),
                 situation=str(data.get("situation") or "").strip(), opening=str(data.get("opening") or "").strip(),
                 grasp=[str(g).strip() for g in data.get("grasp") or [] if str(g).strip()])
    except (TypeError, ValueError):
        return None
    return None if validate(c) else c


async def _draft_case(cu, user, module: str, session: str) -> Case:
    mod, unit = _module_unit(module, session)
    passages = await grounding.retrieve(mod.kb, f"{unit.title}. {unit.outcomes}", PASSAGES, corpus=mod.title) if mod.kb else []
    if not passages:
        raise HTTPException(503, "Yaxa couldn't find this session's readings in the library yet.")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's limit. It resets tomorrow.")
    context = prompting._module_block(mod, unit) + "\n\nCourse passages:\n\n" + prompting.number_passages(passages)
    for _attempt in range(2):  # models occasionally return malformed JSON; one retry
        try:
            reply = await complete_text(config, [{"role": "system", "content": DRAFT_PROMPT},
                                                 {"role": "user", "content": context}], max_tokens=3000)
        except Exception as exc:
            logger.exception("yaxa cases: drafting failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        case = _parse_case(parse_json_reply(reply), module, session)
        if case:
            return case
        logger.warning("yaxa cases: unusable draft: %s", _short(reply, 300))
    raise HTTPException(502, "Yaxa's draft didn't follow the rules twice. Try again.")


@admin_router.get("/{module}")
async def admin_list(module: str) -> list[dict[str, Any]]:
    _require_staff()
    mod = get_catalog().module(module)
    if not mod:
        raise HTTPException(404, "Unknown module")
    rows = []
    for u in mod.units:
        c = load_case(module, u.id)
        rows.append({"session": u.id, "title": u.title, "case_title": c.title if c else "", "status": c.status if c else "none"})
    return rows


@admin_router.get("/{module}/{session}")
async def admin_get(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    c = load_case(module, session)
    return c.model_dump() if c else {"module": module, "session": session, "status": "none", "version": 0,
                                     "title": "", "situation": "", "opening": "", "grasp": []}


@admin_router.post("/{module}/{session}/draft")
async def admin_draft(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    old = load_case(module, session)
    c = await _draft_case(cu, user, module, session)
    c.version = (old.version + 1) if old else 1
    save_case(c)  # a fresh draft is never live: faculty approve it first
    return c.model_dump()


@admin_router.put("/{module}/{session}")
async def admin_save(module: str, session: str, body: EditBody) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    old = load_case(module, session) or Case(module=module, session=session, version=0)
    c = old.model_copy(update={"title": body.title.strip(), "situation": body.situation.strip(), "opening": body.opening.strip(),
                               "grasp": [g.strip() for g in body.grasp if g.strip()], "version": old.version + 1})
    problems = validate(c)
    if problems:
        raise HTTPException(400, {"problems": problems})
    save_case(c)  # edits keep an approved case approved
    return c.model_dump()


@admin_router.post("/{module}/{session}/approve")
async def admin_approve(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    c = load_case(module, session)
    if not c:
        raise HTTPException(404, "Draft the case first")
    problems = validate(c)
    if problems:
        raise HTTPException(400, {"problems": problems})
    c.status, c.approved_by, c.approved_at = "approved", _staff_name(cu, user), now()
    save_case(c)
    return c.model_dump()


@admin_router.post("/{module}/{session}/unpublish")
async def admin_unpublish(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    c = load_case(module, session)
    if not c:
        raise HTTPException(404, "No case for this session")
    c.status = "draft"
    save_case(c)
    return c.model_dump()


# ------------------------------------------------------------------ learners: the case, progress, explain-back
def _progress_path(user_id: str):
    return store.yaxa_root() / "learn" / f"{store._safe(user_id)}.json"  # private to the student


def learn_progress(user_id: str) -> dict[str, dict[str, Any]]:
    return store._read_json(_progress_path(user_id)) or {}


def mark_learn(user_id: str, module: str, session: str, **fields: Any) -> None:
    data = learn_progress(user_id)
    data.setdefault(f"{module}/{session}", {}).update(fields)
    store._write_json(_progress_path(user_id), data)


def learn_status(user_id: str, module: str, session: str) -> dict[str, Any]:
    c = load_case(module, session)
    row = learn_progress(user_id).get(f"{module}/{session}", {})
    return {"case": bool(c and c.status == "approved"), "status": row.get("status", "not_started"),
            "conversation_id": row.get("conversation_id")}


def approved_case(module: str, session: str) -> Case | None:
    c = load_case(module, session)
    return c if c and c.status == "approved" else None


def _session_unit(module: str, session: str):
    cu, user = _me()
    mod = _require_module(get_catalog(), cu, user, module)
    if not mod or not any(u.id == session for u in mod.units):
        raise HTTPException(404, "No such session in this module")
    return cu, user, mod


@router.get("/{module}/{session}")
async def learner_get(module: str, session: str) -> dict[str, Any]:
    cu, _user, _mod = _session_unit(module, session)
    c = approved_case(module, session)
    if not c:
        raise HTTPException(404, "This session doesn't have a case yet")
    return public_view(c) | {"learn": learn_status(cu.id, module, session)}


EXPLAIN_PROMPT = """\
A learner in a Takshashila public policy course has just worked through a case and now explains this
session's idea back in their own words. The notes below say what a learner who has understood the idea can
say; they mix the session's core idea (the concept itself) with how it applies to this particular case.
Judge only whether the learner has the core idea. Judge understanding, not wording, grammar or length.
Never give a score.
- "got": the parts of the core idea their explanation covers, as short statements (may be empty).
- "missing": parts of the core idea it does not cover or gets wrong (empty if they have it). Never list
  case-specific applications here.
- "next": 1-3 questions that take the idea further into this case (applications they did not mention).
  These are invitations to think, not gaps.
- "feedback": 2-4 sentences to the learner, second person, warm and direct: what is right, and for anything
  missing a question that points them towards it, without giving the answer away.
Plain text, no markdown.

Reply with JSON only, no other text:
{"got": ["..."], "missing": ["..."], "next": ["..."], "feedback": "..."}"""


class ExplainBody(BaseModel):
    text: str


def _parse_judgement(data: dict | None) -> dict[str, Any] | None:
    if not isinstance(data, dict) or not isinstance(data.get("feedback"), str):
        return None
    got, missing = data.get("got"), data.get("missing")
    if not isinstance(got, list) or not isinstance(missing, list):
        return None
    nxt = data.get("next") if isinstance(data.get("next"), list) else []
    return {"got": [str(g) for g in got], "missing": [str(m) for m in missing], "next": [str(n) for n in nxt][:3],
            "feedback": data["feedback"].strip()}


@router.post("/{module}/{session}/explain")
async def explain(module: str, session: str, body: ExplainBody) -> dict[str, Any]:
    cu, user, mod = _session_unit(module, session)
    c = approved_case(module, session)
    if not c:
        raise HTTPException(404, "This session doesn't have a case yet")
    text = body.text.strip()
    if len(text.split()) < MIN_EXPLAIN_WORDS:
        raise HTTPException(400, "Write a few sentences in your own words")
    if len(text) > 6000:
        raise HTTPException(413, "That's too long: a short paragraph is enough")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's question limit. It resets tomorrow.")
    unit = next(u for u in mod.units if u.id == session)
    context = (f"{prompting._module_block(mod, unit)}\n\nThe case: {c.title}\n{c.situation}\n\n"
               "What a learner who has understood the idea can say:\n" + "\n".join(f"- {g}" for g in c.grasp)
               + f"\n\nThe learner's explanation:\n{text}")
    for _attempt in range(2):
        try:
            reply = await complete_text(config, [{"role": "system", "content": EXPLAIN_PROMPT},
                                                 {"role": "user", "content": context}], max_tokens=1200)
        except Exception as exc:
            logger.exception("yaxa cases: explain-back failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        result = _parse_judgement(parse_json_reply(reply))
        if result:
            break
        logger.warning("yaxa cases: unusable judgement: %s", _short(reply, 300))
    else:
        raise HTTPException(502, "Yaxa couldn't read your explanation just now. Try again.")
    row = learn_progress(cu.id).get(f"{module}/{session}", {})
    attempts = (row.get("attempts") or [])[-(KEEP_ATTEMPTS - 1):] + [result | {"text": text, "at": now()}]
    status = "explained" if not result["missing"] or row.get("status") == "explained" else "tried"
    mark_learn(cu.id, module, session, status=status, attempts=attempts)
    return result
