"""After the session: for one cohort's live session, a short note faculty approve: what we
discussed, and what is still open, plus a link to the recording. Yaxa can draft it from a
session transcript in the library (transcripts there are already redacted to the lecturer's
voice, with student names removed). Students of that cohort see the approved note on the
module page, under the session. Stored in ``<data>/yaxa/after/<COHORT>/<SESSION>.json``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import store
from .access import _me, _privileged, parse_json_reply
from .catalog import get_catalog
from .grounding import admin_kb_base_dir
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_ITEMS, MAX_ITEM = 6, 400
MAX_TRANSCRIPT = 60_000

PROMPT = """\
You write a short note for students of a Takshashila public policy course, after a live session.
From the session transcript (the lecturer's voice; student names have been removed), write:
- "discussed": 3 to 5 points the session actually covered, each one plain sentence under 30 words;
- "open": 1 to 3 questions the session left open or argued about without settling, each under 25 words.
Only what the transcript supports. Never name or describe a student. Takshashila's usage: "State" means the
political institution in Max Weber's sense. Plain text, no markdown.
Reply with JSON only: {"discussed": ["..."], "open": ["..."]}"""


class DraftBody(BaseModel):
    file: str


class EditBody(BaseModel):
    discussed: list[str]
    open: list[str] = []
    recording_url: str = ""


def _path(cohort: str, session: str):
    return store.yaxa_root() / "after" / cohort / f"{session}.json"


def _load(cohort: str, session: str) -> dict[str, Any] | None:
    data = store._read_json(_path(cohort, session))
    return data if isinstance(data, dict) else None


def approved_note(cohort: str | None, module: str, session: str) -> dict[str, Any] | None:
    n = _load(cohort, session) if cohort else None
    if not n or n.get("status") != "approved" or n.get("module") != module:
        return None
    return {k: n.get(k) for k in ("discussed", "open", "recording_url")}


def _staff(cohort: str, module: str, session: str):
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Faculty and staff only")
    from .schedule import load_cohort  # late: schedule's import chain reaches prepare, which imports this module

    try:
        c = load_cohort(cohort)
    except ValueError:
        c = None
    if not c:
        raise HTTPException(404, "No such cohort")
    mod = get_catalog().modules.get(module)
    if not mod or not any(u.id == session for u in mod.units):
        raise HTTPException(404, "No such session in this module")
    return cu, user


def transcripts(module: str, session: str) -> list[dict[str, Any]]:
    """The session's recording transcripts in the library, newest first."""
    from .module_page import module_groups  # late: module_page imports team, which imports access

    mod = get_catalog().modules[module]
    rows = [r for r in module_groups(get_catalog(), mod).get(session, []) if r.get("kind") == "video" and r.get("open")]
    out = []
    for r in rows:
        name = r["open"].rsplit("/", 1)[-1]
        path = admin_kb_base_dir() / mod.kb / "raw" / name
        if path.is_file():
            out.append({"file": name, "title": r["title"], "path": path})
    return sorted(out, key=lambda t: t["path"].stat().st_mtime, reverse=True)


def _clean(items: list[str]) -> list[str]:
    return [" ".join(str(i).split())[:MAX_ITEM] for i in items if str(i).strip()][:MAX_ITEMS]


def _view(n: dict[str, Any] | None, module: str, session: str) -> dict[str, Any]:
    base = {"module": module, "session": session, "status": "none", "discussed": [], "open": [], "recording_url": ""}
    return base | (n or {})


@router.get("/after/{cohort}/{module}/{session}")
async def get_note(cohort: str, module: str, session: str) -> dict[str, Any]:
    _staff(cohort, module, session)
    return _view(_load(cohort, session), module, session) | {
        "transcripts": [{"file": t["file"], "title": t["title"]} for t in transcripts(module, session)]}


@router.post("/after/{cohort}/{module}/{session}/draft")
async def draft(cohort: str, module: str, session: str, body: DraftBody) -> dict[str, Any]:
    cu, _ = _staff(cohort, module, session)
    t = next((t for t in transcripts(module, session) if t["file"] == body.file), None)
    if not t:
        raise HTTPException(404, "That transcript isn't in this session's library")
    text = t["path"].read_text(encoding="utf-8", errors="replace")[:MAX_TRANSCRIPT]
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    for _ in range(2):
        try:
            reply = await complete_text(config, [{"role": "system", "content": PROMPT},
                                                 {"role": "user", "content": f"Session {session}.\n\nTranscript:\n{text}"}], max_tokens=1200)
        except Exception as exc:
            logger.exception("yaxa after: drafting failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        data = parse_json_reply(reply)
        if isinstance(data, dict) and _clean(data.get("discussed") or []):
            old = _load(cohort, session) or {}
            n = {"module": module, "session": session, "status": "draft", "discussed": _clean(data["discussed"]),
                 "open": _clean(data.get("open") or []), "recording_url": old.get("recording_url", ""), "from": t["title"]}
            store._write_json(_path(cohort, session), n)
            return _view(n, module, session)
    raise HTTPException(502, "Yaxa's draft didn't come out right twice. Try again.")


@router.put("/after/{cohort}/{module}/{session}")
async def save(cohort: str, module: str, session: str, body: EditBody) -> dict[str, Any]:
    _staff(cohort, module, session)
    discussed = _clean(body.discussed)
    if not discussed:
        raise HTTPException(400, "Write at least one point the session covered")
    url = body.recording_url.strip()
    if url and not url.startswith("https://"):
        raise HTTPException(400, "The recording link must start with https://")
    old = _load(cohort, session) or {}
    n = old | {"module": module, "session": session, "discussed": discussed, "open": _clean(body.open),
               "recording_url": url, "status": old.get("status", "draft")}
    store._write_json(_path(cohort, session), n)
    return _view(n, module, session)


@router.post("/after/{cohort}/{module}/{session}/approve")
async def approve(cohort: str, module: str, session: str) -> dict[str, Any]:
    _staff(cohort, module, session)
    n = _load(cohort, session)
    if not n or not n.get("discussed"):
        raise HTTPException(404, "Write or draft the note first")
    n |= {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat()}
    store._write_json(_path(cohort, session), n)
    return _view(n, module, session)


@router.post("/after/{cohort}/{module}/{session}/unpublish")
async def unpublish(cohort: str, module: str, session: str) -> dict[str, Any]:
    _staff(cohort, module, session)
    n = _load(cohort, session)
    if not n:
        raise HTTPException(404, "No note for this session")
    n["status"] = "draft"
    store._write_json(_path(cohort, session), n)
    return _view(n, module, session)
