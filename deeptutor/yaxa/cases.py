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
from .access import _me, _privileged, _short, parse_json_reply
from .catalog import get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)

MIN_WORDS = 80
MAX_WORDS = 400
MIN_GRASP = 2
MAX_GRASP = 5
PASSAGES = 10

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
