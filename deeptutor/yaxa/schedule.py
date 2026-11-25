"""Cohort life: each cohort's schedule, joining a cohort by link, and the learner's week.

A cohort (GCPP45) is one batch of learners in a programme. Its file,
``<data>/yaxa/cohorts/<CODE>.yaml``, holds the sessions (by LMS session code,
CS12, CT31, ...) with their dates, other key dates (deadlines, debates), the
join link code, and the email group announcements go to.

All dates and times are IST. A learner sees only their own cohort, and only
sessions of modules they can open.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import re
import secrets
import tempfile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from . import store
from .access import _me
from .catalog import get_catalog

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))
_CODE = re.compile(r"^[A-Z0-9-]{2,20}$")


class Session(BaseModel):
    code: str  # LMS session code, the unit id: CS12, CT31
    date: str  # YYYY-MM-DD, IST
    time: str = ""  # HH:MM, IST; empty for a whole-day item
    host: str = ""
    webinar_url: str = ""
    note: str = ""


class KeyDate(BaseModel):
    date: str
    label: str
    track: str | None = None  # only for this track's members, when set


class Cohort(BaseModel):
    code: str
    programme: str
    start: str = ""
    email_group: str = ""
    track_email_groups: dict[str, str] = Field(default_factory=dict)
    join_code: str = ""
    join_open: bool = True
    sessions: list[Session] = Field(default_factory=list)
    dates: list[KeyDate] = Field(default_factory=list)


# ------------------------------------------------------------------ storage
def _dir() -> Path:
    return store.yaxa_root() / "cohorts"


def _path(code: str) -> Path:
    if not _CODE.match(code or ""):
        raise ValueError(f"bad cohort code: {code!r}")
    return _dir() / f"{code}.yaml"


def load_cohort(code: str) -> Cohort | None:
    path = _path(code)
    if not path.is_file():
        return None
    return Cohort(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))


def save_cohort(c: Cohort) -> None:
    path = _path(c.code)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(c.model_dump(), fh, sort_keys=False, allow_unicode=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def list_cohorts() -> list[Cohort]:
    if not _dir().is_dir():
        return []
    out = []
    for p in sorted(_dir().glob("*.yaml")):
        try:
            c = load_cohort(p.stem)
        except ValueError:
            continue
        if c:
            out.append(c)
    return out


def cohort_by_join_code(code: str) -> Cohort | None:
    if not code:
        return None
    return next((c for c in list_cohorts() if secrets.compare_digest(c.join_code, code)), None)


def new_join_code() -> str:
    return secrets.token_urlsafe(8)[:10]


def _shift(day: str, weeks: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=7 * weeks)).isoformat()


def copy_schedule(src: Cohort, code: str, weeks: int) -> Cohort:
    """Next cohort's schedule: the same sessions and dates, `weeks` later, with its own join link."""
    return src.model_copy(
        update={
            "code": code,
            "start": _shift(src.start, weeks) if src.start else "",
            "join_code": new_join_code(),
            "join_open": True,
            "sessions": [s.model_copy(update={"date": _shift(s.date, weeks), "webinar_url": ""}) for s in src.sessions],
            "dates": [d.model_copy(update={"date": _shift(d.date, weeks)}) for d in src.dates],
        }
    )


def starts_at(s: Session) -> datetime:
    hh, mm = (int(x) for x in s.time.split(":")) if s.time else (0, 0)
    return datetime.combine(date.fromisoformat(s.date), time(hh, mm), tzinfo=IST)


# ------------------------------------------------------------------ joining
CLOSED = "This link is no longer open"


def _open_cohort(code: str) -> Cohort:
    c = cohort_by_join_code(code)
    if not c or not c.join_open:
        raise HTTPException(404, CLOSED)
    return c


@router.get("/join/{code}")
async def join_preview(code: str) -> dict:
    c = _open_cohort(code)
    prog = get_catalog().programme(c.programme)
    return {
        "cohort": c.code,
        "programme": c.programme,
        "programme_name": prog.name if prog else c.programme,
        "tracks": [{"code": t.code, "name": t.name} for t in (prog.tracks if prog else [])],
        "open": True,
    }


class JoinBody(BaseModel):
    track: str | None = None


@router.post("/join/{code}")
async def join(code: str, body: JoinBody) -> dict:
    """Enrol in the link's cohort. Works even when self-enrolment is off: the link is the invitation."""
    _, user = _me()
    c = _open_cohort(code)
    prog = get_catalog().programme(c.programme)
    if not prog:
        raise HTTPException(404, CLOSED)
    old = next((e for e in user.enrolments if e.programme == prog.code), None)
    track = body.track or (old.track if old else None)
    if body.track and not prog.track(body.track):
        raise HTTPException(400, f"{prog.code} has no track {body.track}")
    user.enrolments = [e for e in user.enrolments if e.programme != prog.code]
    user.enrolments.append(store.Enrolment(programme=prog.code, track=track, cohort=c.code))
    store.save_user(user)
    return {"ok": True, "programme": prog.code, "cohort": c.code, "track": track}
