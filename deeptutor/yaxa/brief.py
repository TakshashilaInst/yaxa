"""The brief: each student's own policy brief, built one layer per session through the course.

The student names a problem of their own (any topic; it can change). Each session with an approved layer
prompt (layers.py) asks them to apply that session's idea to their problem, and to rate themselves on a short
self-check. On request Yaxa questions their reasoning, with cited web results and course passages; it never
rewrites their text. In the final week they also take one unseen topic.

Privacy: a brief lives in one file per student and is returned only to that student. No route here, or
anywhere else, gives faculty a student's brief. The Friday brief (sprint_brief.py) reads texts only to
produce anonymised patterns across at least three students.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import grounding, layers, prompting, store
from .access import _allowed_modules, _me, _require_module, _short, parse_json_reply
from .catalog import get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)

MAX_TITLE = 120
MAX_PROBLEM = 4000
MAX_LAYER = 12000
MIN_CRITIQUE_WORDS = 40
KEEP_CRITIQUES = 3
WEB_RESULTS = 5
PASSAGES = 4
RATINGS = ("no", "partly", "yes")
TRACK_DOMAINS = {"TP": "technology policy", "APP": "Indian domestic public policy", "DFA": "foreign policy and strategic affairs"}

router = APIRouter(prefix="/brief")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ storage (private, one file per student)
def _path(user_id: str):
    return store.yaxa_root() / "briefs" / f"{store._safe(user_id)}.json"


def load(user_id: str) -> dict[str, Any]:
    data = store._read_json(_path(user_id)) or {}
    data.setdefault("problem", {"title": "", "text": "", "updated_at": ""})
    data.setdefault("layers", {})
    data.setdefault("unseen", {"topic": "", "text": "", "proposed_at": "", "updated_at": ""})
    return data


def _save(user_id: str, data: dict[str, Any]) -> None:
    store._write_json(_path(user_id), data)


def layer_status(user_id: str, module: str, session: str) -> dict[str, bool]:
    """For the sprint steps: is there an approved layer, and has this student written it."""
    row = load(user_id)["layers"].get(f"{module}/{session}", {})
    return {"available": layers.approved_layer(module, session) is not None, "written": bool((row.get("text") or "").strip())}


def layer_texts(user_ids: list[str], module: str, session: str) -> list[str]:
    """The written layer texts of these students, for anonymised aggregation only (sprint_brief.py)."""
    out = []
    for uid in user_ids:
        text = (load(uid)["layers"].get(f"{module}/{session}", {}).get("text") or "").strip()
        if text:
            out.append(text)
    return out


# ------------------------------------------------------------------ reading and writing
def _approved_for(module: str, session: str):
    cu, user = _me()
    mod = _require_module(get_catalog(), cu, user, module)
    unit = next((u for u in mod.units if u.id == session), None) if mod else None
    layer = layers.approved_layer(module, session) if unit else None
    if not layer:
        raise HTTPException(404, "This session doesn't have a brief layer yet")
    return cu, user, mod, unit, layer


@router.get("")
async def get_brief() -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    data = load(cu.id)
    rows = []
    for code in _allowed_modules(cat, cu, user):
        mod = cat.modules.get(code)
        if not mod:
            continue
        for unit in mod.units:
            layer = layers.approved_layer(code, unit.id)
            if not layer:
                continue
            mine = data["layers"].get(f"{code}/{unit.id}", {})
            rows.append({"module": code, "module_title": mod.title, "session": unit.id, "title": unit.title,
                         "prompt": layer.prompt, "self_check": layer.self_check, "text": mine.get("text", ""),
                         "ratings": mine.get("ratings", {}), "critiques": mine.get("critiques", []),
                         "updated_at": mine.get("updated_at", "")})
    return {"problem": data["problem"], "layers": rows, "unseen": data["unseen"]}


class ProblemBody(BaseModel):
    title: str
    text: str = ""


@router.put("/problem")
async def put_problem(body: ProblemBody) -> dict[str, Any]:
    cu, _user = _me()
    title, text = body.title.strip(), body.text.strip()
    if not title:
        raise HTTPException(400, "Give your problem a name")
    if len(title) > MAX_TITLE or len(text) > MAX_PROBLEM:
        raise HTTPException(413, "That's too long: a name and a short paragraph are enough")
    data = load(cu.id)
    data["problem"] = {"title": title, "text": text, "updated_at": now()}
    _save(cu.id, data)
    return data["problem"]


class LayerBody(BaseModel):
    text: str = ""
    ratings: dict[str, str] = Field(default_factory=dict)  # self-check index -> no | partly | yes


@router.put("/layers/{module}/{session}")
async def put_layer(module: str, session: str, body: LayerBody) -> dict[str, Any]:
    cu, _user, _mod, _unit, layer = _approved_for(module, session)
    if len(body.text) > MAX_LAYER:
        raise HTTPException(413, "That's too long for one layer")
    for k, v in body.ratings.items():
        if v not in RATINGS or not k.isdigit() or int(k) >= len(layer.self_check):
            raise HTTPException(400, "Rate each statement no, partly or yes")
    data = load(cu.id)
    row = data["layers"].setdefault(f"{module}/{session}", {})
    row.update({"text": body.text.strip(), "ratings": dict(body.ratings), "updated_at": now()})
    _save(cu.id, data)
    return row


# ------------------------------------------------------------------ critique on request
CRITIQUE_PROMPT = """\
You are Yaxa, questioning a working professional's reasoning in their own policy brief for a Takshashila course.
They are applying this session's idea to a problem they chose. Your job is to make their thinking sharper.
- Never rewrite their text and never draft sentences for their brief. Do not offer improved versions.
- Do say plainly when something is wrong, and why ("that's a symptom, not a market failure, because...").
- Ask 2-4 pointed questions that expose gaps: missing actors, untested assumptions, evidence they need, what
  the session's idea would make them notice.
- Use the web results [W1]... and course passages [C1]... for facts, and cite them inline. Never invent sources.
  If a result is irrelevant, ignore it.
- Under 250 words, second person, plain text, no markdown headings. Reply with the critique only.
Takshashila's usage: "State" means the political institution in Max Weber's sense, never an Indian
sub-national state."""


def _web_search(query: str) -> list[dict[str, str]]:
    """Web results for a critique. DuckDuckGo needs no key, so this works whichever model the student uses."""
    from deeptutor.services.search import web_search

    r = web_search(query, provider="duckduckgo")
    return [{"title": str(x.get("title") or ""), "url": str(x.get("url") or ""), "snippet": str(x.get("snippet") or "")}
            for x in (r.get("search_results") or [])[:WEB_RESULTS] if x.get("url")]


async def _critique(cu, user, *, mod, unit, task: str, problem: str, text: str) -> dict[str, Any]:
    if len(text.split()) < MIN_CRITIQUE_WORDS:
        raise HTTPException(400, f"Write at least {MIN_CRITIQUE_WORDS} words first: Yaxa questions your reasoning, it doesn't start it")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's question limit. It resets tomorrow.")
    query = f"{problem or ' '.join(text.split()[:12])} India"
    try:
        web = await asyncio.to_thread(_web_search, query)
    except Exception:  # noqa: BLE001 - critique still works from the course passages
        logger.warning("yaxa brief: web search failed", exc_info=True)
        web = []
    passages = []
    if mod and mod.kb:
        try:
            passages = await grounding.retrieve(mod.kb, f"{task} {problem}", PASSAGES, corpus=mod.title)
        except Exception:  # noqa: BLE001
            logger.warning("yaxa brief: retrieval failed", exc_info=True)
    web_block = "\n".join(f"[W{i}] {w['title']} ({w['url']}): {w['snippet']}" for i, w in enumerate(web, 1)) or "(none)"
    course_block = "\n\n".join(f"[C{i}] {prompting.passage_label(p)}\n{p.get('text', '')}" for i, p in enumerate(passages, 1)) or "(none)"
    context = (prompting._module_block(mod, unit) + f"\n\nThe layer task: {task}\n\nTheir problem: {problem or '(not named yet)'}"
               f"\n\nWeb results:\n{web_block}\n\nCourse passages:\n{course_block}\n\nTheir text:\n{text}")
    for _attempt in range(2):
        try:
            reply = await complete_text(config, [{"role": "system", "content": CRITIQUE_PROMPT},
                                                 {"role": "user", "content": context}], max_tokens=1600)
        except Exception as exc:
            logger.exception("yaxa brief: critique failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        data = parse_json_reply(reply) if reply.lstrip().startswith(("{", "```")) else None
        text_out = data.get("critique") if isinstance(data, dict) else reply  # plain text; older prompts asked for JSON
        if isinstance(text_out, str) and text_out.strip():
            sources = [{"ref": f"W{i}", "title": w["title"], "url": w["url"]} for i, w in enumerate(web, 1)]
            sources += [{"ref": f"C{i}", "title": prompting.passage_label(p), "url": ""} for i, p in enumerate(passages, 1)]
            return {"critique": text_out.strip(), "sources": sources, "at": now()}
        logger.warning("yaxa brief: unusable critique: %s", _short(reply, 300))
    raise HTTPException(502, "Yaxa couldn't write a critique just now. Try again.")


@router.post("/layers/{module}/{session}/critique")
async def critique(module: str, session: str) -> dict[str, Any]:
    cu, user, mod, unit, layer = _approved_for(module, session)
    data = load(cu.id)
    row = data["layers"].get(f"{module}/{session}", {})
    out = await _critique(cu, user, mod=mod, unit=unit, task=layer.prompt, problem=data["problem"]["title"],
                          text=(row.get("text") or "").strip())
    data = load(cu.id)  # re-read: the model call took a while
    row = data["layers"].setdefault(f"{module}/{session}", {})
    row["critiques"] = (row.get("critiques") or [])[-(KEEP_CRITIQUES - 1):] + [out]
    _save(cu.id, data)
    return out


# ------------------------------------------------------------------ the final week's unseen topic
UNSEEN_PROMPT = """\
Propose one fresh, real policy problem for a working professional at the end of a Takshashila public policy
course to analyse unaided with everything they learned (the policy system, State and government, types of
intervention, markets and market failures, complexity, Bardach's eightfold path). It must be in the domain given,
current, concrete, and Indian or with clear Indian stakes. One line, under 20 words, no explanation.

Reply with JSON only, no other text:
{"topic": "<text>"}"""


class UnseenBody(BaseModel):
    replace: bool = False


class UnseenText(BaseModel):
    text: str


@router.post("/unseen")
async def propose_unseen(body: UnseenBody) -> dict[str, Any]:
    cu, user = _me()
    data = load(cu.id)
    if (data["unseen"].get("text") or "").strip() and not body.replace:
        raise HTTPException(409, "You've already written on your unseen topic")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    track = next((e.track for e in user.enrolments if e.track), None)
    domain = TRACK_DOMAINS.get(track or "", "public policy")
    avoid = data["problem"]["title"]
    try:
        reply = await complete_text(config, [{"role": "system", "content": UNSEEN_PROMPT},
                                             {"role": "user", "content": f"Domain: {domain}. Not this one: {avoid or '-'}"}],
                                    max_tokens=200)
    except Exception as exc:
        raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
    topic = str((parse_json_reply(reply) or {}).get("topic") or "").strip()
    if not topic:
        raise HTTPException(502, "Yaxa couldn't propose a topic just now. Try again.")
    data = load(cu.id)
    data["unseen"] = {"topic": topic[:200], "text": "", "proposed_at": now(), "updated_at": ""}
    _save(cu.id, data)
    return data["unseen"]


@router.put("/unseen")
async def put_unseen(body: UnseenText) -> dict[str, Any]:
    cu, _user = _me()
    data = load(cu.id)
    if not data["unseen"].get("topic"):
        raise HTTPException(404, "Ask Yaxa for an unseen topic first")
    if len(body.text) > MAX_LAYER:
        raise HTTPException(413, "That's too long")
    data["unseen"].update({"text": body.text.strip(), "updated_at": now()})
    _save(cu.id, data)
    return data["unseen"]


@router.post("/unseen/critique")
async def critique_unseen() -> dict[str, Any]:
    cu, user = _me()
    u = load(cu.id)["unseen"]
    if not u.get("topic"):
        raise HTTPException(404, "Ask Yaxa for an unseen topic first")
    out = await _critique(cu, user, mod=None, unit=None, task="Analyse an unseen topic with the whole framework, unaided.",
                          problem=u["topic"], text=(u.get("text") or "").strip())
    data = load(cu.id)
    data["unseen"]["critiques"] = (data["unseen"].get("critiques") or [])[-(KEEP_CRITIQUES - 1):] + [out]
    _save(cu.id, data)
    return out


# ------------------------------------------------------------------ ownership: download it
@router.get("/export")
async def export() -> Response:
    b = await get_brief()
    title = b["problem"]["title"] or "My policy brief"
    parts = [f"# {title}", ""]
    if b["problem"]["text"]:
        parts += [b["problem"]["text"], ""]
    for r in b["layers"]:
        if not r["text"]:
            continue
        parts += [f"## {r['session']} · {r['title']}", "", f"*{r['prompt']}*", "", r["text"], ""]
        rated = [f"- {q}: {r['ratings'][str(i)]}" for i, q in enumerate(r["self_check"]) if str(i) in r["ratings"]]
        if rated:
            parts += ["Self-check:", *rated, ""]
    u = b["unseen"]
    if u.get("topic") and u.get("text"):
        parts += [f"## Unseen topic: {u['topic']}", "", u["text"], ""]
    return Response("\n".join(parts), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="my-policy-brief.md"'})
