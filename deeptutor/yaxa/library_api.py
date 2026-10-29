"""Libraries page: sync status, "Sync now", and the student-name review queue.

Admins and faculty only. The web app never talks to Drive or Sarvam: it reads
the sync's ledger and leaves a request file the worker picks up.
"""

from __future__ import annotations

from collections import Counter
import json
import shutil
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.multi_user.audit import log_admin_action

from .access import _me, _privileged
from .library import sync
from .library.ledger import Ledger, now
from .library.redaction import apply_review

router = APIRouter(prefix="/library")


def _require_staff() -> Any:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "The Libraries page is for Takshashila staff")
    return cu


def _ledger() -> Ledger:
    return Ledger(sync.library_root() / "ledger.json").load()


def _public_full() -> set[str]:
    path = sync.library_root() / "public-names.json"
    return set(json.loads(path.read_text()).get("full", [])) if path.is_file() else set()


def _running() -> bool:
    with sync.lock() as got:
        return not got


def _queue_sync() -> None:
    sync.library_root().mkdir(parents=True, exist_ok=True)
    (sync.library_root() / "request").write_text(now())


@router.get("")
async def status() -> dict[str, Any]:
    _require_staff()
    led = _ledger()
    by_kb: dict[str, Counter[str]] = {}
    for e in led.entries.values():
        if e.kb:
            by_kb.setdefault(e.kb, Counter())[e.status] += 1
    try:
        last_run = json.loads((sync.library_root() / "last_run.json").read_text())
    except (FileNotFoundError, ValueError):
        last_run = None
    return {
        "last_run": last_run,
        "running": _running(),
        "queued": (sync.library_root() / "request").exists(),
        "needs_review": sum(e.status == "review" for e in led.entries.values()),
        "libraries": [{"kb": kb, "counts": dict(c)} for kb, c in sorted(by_kb.items())],
        "problems": [
            {"drive_id": e.drive_id, "path": e.path, "status": e.status, "error": e.error}
            for e in led.entries.values() if e.status in ("failed", "skipped")
        ],
    }


@router.post("/sync")
async def request_sync() -> dict[str, bool]:
    _require_staff()
    _queue_sync()
    return {"queued": True}


@router.get("/review")
async def review_queue() -> list[dict[str, Any]]:
    _require_staff()
    return [
        {"drive_id": e.drive_id, "path": e.path, "title": e.placement.get("title", ""), "flags": e.flags}
        for e in _ledger().entries.values() if e.status == "review"
    ]


class Decision(BaseModel):
    decisions: dict[str, Literal["keep", "remove"]] = Field(default_factory=dict)
    reject: bool = False


@router.post("/review/{drive_id}")
async def decide(drive_id: str, body: Decision) -> dict[str, str]:
    cu = _require_staff()
    led = _ledger()
    entry = led.entries.get(drive_id)
    if not entry or entry.status != "review":
        raise HTTPException(404, "Nothing waiting for review with that id")
    private = sync.library_root() / "private" / drive_id
    if body.reject:
        shutil.rmtree(private, ignore_errors=True)
        entry.status, entry.flags, entry.updated = "rejected", [], now()
        entry.error = "not used: a reviewer chose not to use this recording"
        led.save()
        log_admin_action("yaxa_library_reject", summary={"drive_id": drive_id, "by": getattr(cu, "id", "")})
        return {"status": "rejected"}
    flagged = {f["name"] for f in entry.flags}
    if flagged - set(body.decisions):
        raise HTTPException(400, "Decide on every flagged name first")
    transcript = private / "redacted.md"
    if not transcript.is_file():
        raise HTTPException(409, "The transcript is missing; the next sync will redo it")
    transcript.write_text(apply_review(transcript.read_text(encoding="utf-8"), body.decisions, _public_full()), encoding="utf-8")
    entry.allow = sorted(set(entry.allow) | {n for n, d in body.decisions.items() if d == "keep"})
    entry.status, entry.flags, entry.updated = "approved", [], now()
    led.save()
    _queue_sync()
    # counts only: the names themselves never go into the audit log
    log_admin_action("yaxa_library_review", summary={
        "drive_id": drive_id, "by": getattr(cu, "id", ""),
        "kept": sum(d == "keep" for d in body.decisions.values()),
        "removed": sum(d == "remove" for d in body.decisions.values()),
    })
    return {"status": "approved"}
