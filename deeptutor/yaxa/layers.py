"""Brief layer prompts: what each session asks the student to add to their own brief.

Through the course each student builds a brief on a problem of their own choosing. Each session adds one
layer to it (the mapping below follows the course design, and is attached to sessions, not week numbers).
Yaxa drafts the layer task and a 3-5 question self-check from the session; faculty edit and approve, as
with weekly cases. Students see approved layers only. The briefs themselves live in brief.py and are
private to each student.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import community, prompting, store
from .access import _me, _privileged, _short, parse_json_reply
from .catalog import get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)

MIN_PROMPT_WORDS = 8
MAX_PROMPT_WORDS = 160
MIN_CHECKS = 3
MAX_CHECKS = 5

admin_router = APIRouter(prefix="/layers/admin")

# The course design's mapping of session ideas to brief layers. Session codes first, then whole modules.
_SESSION_HINTS = {
    "CP10": "My problem as a policy problem: who is affected, the actors involved, and a first sketch of the system around it.",
    "CP11": "Which institutions hold authority over my problem; where their legitimacy comes from; constitutional limits on them.",
    "CP12": "Which institutions hold authority over my problem; where their legitimacy comes from; constitutional limits on them.",
    "CP13": "What government has tried on my problem so far, and which type of intervention each attempt was.",
    "CT23": "Restructure the brief into Bardach's eightfold path; earlier layers become steps 1-3 and step 8.",
    "CT3x": "Bardach step 1: name the market failure behind the symptom in my problem.",
    "CP44": "Bardach step 5: second-order effects and feedback loops if my preferred option is adopted.",
}
_MODULE_HINTS = {
    "GCPP-ER1": "Incentives and evidence: who gains and who loses in my problem, what prices say, and the numbers that size it.",
    "GCPP-COMM": "The 300-word version of my brief for a sceptical reader.",
    "TP-AI": "Domain lens: what the technology itself changes about my problem.",
    "TP-HTG": "Domain lens: the geopolitics of technology as it bears on my problem.",
}


def hint_for(module: str, session: str) -> str:
    """The course design's layer for this session, or "" if the session has none."""
    return _SESSION_HINTS.get(session) or _MODULE_HINTS.get(module, "")


class Layer(BaseModel):
    module: str
    session: str
    status: Literal["draft", "approved"] = "draft"
    version: int = 1
    prompt: str = ""  # the layer task, addressed to the student
    self_check: list[str] = Field(default_factory=list)  # statements the student rates themselves on
    approved_by: str = ""
    approved_at: str = ""


def validate(layer: Layer) -> list[str]:
    problems = []
    n = len(layer.prompt.split())
    if n < MIN_PROMPT_WORDS:
        problems.append(f"The layer task is too short ({n} words; at least {MIN_PROMPT_WORDS})")
    if n > MAX_PROMPT_WORDS:
        problems.append(f"The layer task is too long ({n} words; at most {MAX_PROMPT_WORDS})")
    checks = [c for c in layer.self_check if c.strip()]
    if not MIN_CHECKS <= len(checks) <= MAX_CHECKS:
        problems.append(f"Give {MIN_CHECKS}-{MAX_CHECKS} self-check statements (now {len(checks)})")
    return problems


def _path(module: str, session: str):
    return community.root("layers", store._safe(module)) / f"{store._safe(session)}.json"


def load_layer(module: str, session: str) -> Layer | None:
    data = store._read_json(_path(module, session))
    return Layer(**data) if data else None


def save_layer(layer: Layer) -> None:
    store._write_json(_path(layer.module, layer.session), layer.model_dump())


def approved_layer(module: str, session: str) -> Layer | None:
    layer = load_layer(module, session)
    return layer if layer and layer.status == "approved" else None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ faculty: draft, edit, approve
DRAFT_PROMPT = """\
Takshashila's public policy course for working professionals asks each student to build one policy brief, through
the course, on a problem of their own choosing (any topic: technology, domestic or foreign policy). Each session
adds one layer to that brief. Write this session's layer.
- "prompt": the layer task, 25-90 words, addressed to the student ("your problem"). It asks them to apply this
  session's idea to their own problem. It must work for any problem. Never ask for a grade or word count.
- "self_check": 3-5 short first-person statements the student rates themselves on after writing
  ("I named who loses, not only who gains"). They check use of the idea, not style.
Takshashila's usage: "State" means the political institution in Max Weber's sense, never an Indian sub-national
state. Plain text, no markdown.

Reply with JSON only, no other text:
{"prompt": "<text>", "self_check": ["<statement>", ...]}"""


class EditBody(BaseModel):
    prompt: str
    self_check: list[str]


def _require_staff():
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Layer prompts are edited by faculty")
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


def _parse(data: dict | None, module: str, session: str) -> Layer | None:
    if not isinstance(data, dict):
        return None
    layer = Layer(module=module, session=session, prompt=str(data.get("prompt") or "").strip(),
                  self_check=[str(c).strip() for c in data.get("self_check") or [] if str(c).strip()])
    return None if validate(layer) else layer


async def _draft(cu, user, module: str, session: str) -> Layer:
    mod, unit = _module_unit(module, session)
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's limit. It resets tomorrow.")
    hint = hint_for(module, session)
    context = prompting._module_block(mod, unit) + (
        f"\n\nThe course design says this session's layer is: {hint}" if hint
        else "\n\nThe course design gives no layer for this session: derive one from the session's idea.")
    for _attempt in range(2):
        try:
            reply = await complete_text(config, [{"role": "system", "content": DRAFT_PROMPT},
                                                 {"role": "user", "content": context}], max_tokens=1200)
        except Exception as exc:
            logger.exception("yaxa layers: drafting failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        layer = _parse(parse_json_reply(reply), module, session)
        if layer:
            return layer
        logger.warning("yaxa layers: unusable draft: %s", _short(reply, 300))
    raise HTTPException(502, "Yaxa's draft didn't follow the rules twice. Try again.")


def _empty(module: str, session: str) -> dict[str, Any]:
    return {"module": module, "session": session, "status": "none", "version": 0, "prompt": "", "self_check": []}


@admin_router.get("/{module}")
async def admin_list(module: str) -> list[dict[str, Any]]:
    _require_staff()
    mod = get_catalog().module(module)
    if not mod:
        raise HTTPException(404, "Unknown module")
    rows = []
    for u in mod.units:
        layer = load_layer(module, u.id)
        rows.append({"session": u.id, "title": u.title, "hint": hint_for(module, u.id),
                     "status": layer.status if layer else "none"})
    return rows


@admin_router.get("/{module}/{session}")
async def admin_get(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    layer = load_layer(module, session)
    return (layer.model_dump() if layer else _empty(module, session)) | {"hint": hint_for(module, session)}


@admin_router.post("/{module}/{session}/draft")
async def admin_draft(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    old = load_layer(module, session)
    layer = await _draft(cu, user, module, session)
    layer.version = (old.version + 1) if old else 1
    save_layer(layer)  # a fresh draft is never live
    return layer.model_dump() | {"hint": hint_for(module, session)}


@admin_router.put("/{module}/{session}")
async def admin_save(module: str, session: str, body: EditBody) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    old = load_layer(module, session) or Layer(module=module, session=session, version=0)
    layer = old.model_copy(update={"prompt": body.prompt.strip(), "version": old.version + 1,
                                   "self_check": [c.strip() for c in body.self_check if c.strip()]})
    problems = validate(layer)
    if problems:
        raise HTTPException(400, {"problems": problems})
    save_layer(layer)  # edits keep an approved layer approved
    return layer.model_dump() | {"hint": hint_for(module, session)}


@admin_router.post("/{module}/{session}/approve")
async def admin_approve(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    layer = load_layer(module, session)
    if not layer:
        raise HTTPException(404, "Draft the layer first")
    problems = validate(layer)
    if problems:
        raise HTTPException(400, {"problems": problems})
    layer.status, layer.approved_by, layer.approved_at = "approved", _staff_name(cu, user), now()
    save_layer(layer)
    return layer.model_dump() | {"hint": hint_for(module, session)}


@admin_router.post("/{module}/{session}/unpublish")
async def admin_unpublish(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    layer = load_layer(module, session)
    if not layer:
        raise HTTPException(404, "No layer for this session")
    layer.status = "draft"
    save_layer(layer)
    return layer.model_dump() | {"hint": hint_for(module, session)}
