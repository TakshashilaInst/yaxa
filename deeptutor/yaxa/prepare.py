"""Prepare next week: for a cohort's upcoming sessions, whether each has its weekly case (Learn),
brief layer (Apply) and session check (Check), as none / draft / approved; and one call that
drafts whichever of the three a session is missing. Drafts are never live: faculty review and
approve each one in its own editor. Existing drafts and approved work are never replaced here.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from . import after, cases, checks, layers
from .access import _me, _privileged
from .catalog import get_catalog
from .schedule import load_cohort

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
WINDOW_DAYS = 14


def _today() -> date:
    return datetime.now(IST).date()


def _staff():
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Faculty and staff only")
    return cu, user


def _module_of(session: str) -> tuple[str, str]:
    for m in get_catalog().modules.values():
        for u in m.units:
            if u.id == session or session in u.aliases:
                return m.code, u.title
    return "", ""


def status(module: str, session: str) -> dict[str, str]:
    c, lay, chk = cases.load_case(module, session), layers.load_layer(module, session), checks.load_set(module, session)
    return {
        "case": c.status if c else "none",
        "layer": lay.status if lay else "none",
        "check": chk.status if chk else "none",
    }


@router.get("/prepare/{cohort}")
async def upcoming(cohort: str, all_weeks: bool = False) -> dict[str, Any]:
    _staff()
    try:
        c = load_cohort(cohort)
    except ValueError:
        c = None
    if not c:
        raise HTTPException(404, "No such cohort")
    today, until = _today().isoformat(), (_today() + timedelta(days=WINDOW_DAYS)).isoformat()
    rows = []
    for s in sorted(c.sessions, key=lambda s: (s.date, s.time)):
        if not all_weeks and not (today <= s.date < until):
            continue
        module, title = _module_of(s.code)
        if not module:
            continue
        note = after._load(c.code, s.code)
        rows.append({"session": s.code, "module": module, "title": title, "date": s.date, "time": s.time,
                     "host": s.host, "past": s.date < today, "after": (note or {}).get("status", "none")} | status(module, s.code))
    return {"cohort": c.code, "today": today, "sessions": rows}


@router.post("/prepare/{module}/{session}/draft")
async def draft_missing(module: str, session: str) -> dict[str, Any]:
    """Draft the case, layer and check this session lacks, side by side; keep what exists."""
    cu, user = _staff()
    if not any(u.id == session for u in (get_catalog().modules.get(module).units if get_catalog().modules.get(module) else [])):
        raise HTTPException(404, "No such session in this module")
    have = status(module, session)

    async def case():
        c = await cases._draft_case(cu, user, module, session)
        c.version = 1
        cases.save_case(c)

    async def layer():
        lay = await layers._draft(cu, user, module, session)
        lay.version = 1
        layers.save_layer(lay)

    async def check():
        qs = await checks._draft_questions(cu, user, module, session, checks.QUESTIONS, [])
        checks.save_set(checks.CheckSet(module=module, session=session, questions=qs))

    jobs = [(name, fn) for name, fn in (("case", case), ("layer", layer), ("check", check)) if have[name] == "none"]
    results = await asyncio.gather(*(fn() for _, fn in jobs), return_exceptions=True)
    errors = []
    for (name, _), r in zip(jobs, results):
        if isinstance(r, Exception):
            detail = r.detail if isinstance(r, HTTPException) else str(r)
            errors.append(f"{name}: {detail}")
    return status(module, session) | {"errors": errors}
