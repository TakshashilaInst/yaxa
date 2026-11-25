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

from . import module_page, store
from .access import _allowed_modules, _me, _privileged
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
    closed: bool = False  # once the programme ends: chat and discussion become read-only
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


# ------------------------------------------------------------------ staff
def _staff() -> None:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Faculty and staff only")


def _members(code: str) -> list[store.YaxaUser]:
    return [u for u in store.list_users() if any(e.cohort == code for e in u.enrolments)]


def _need(code: str) -> Cohort:
    try:
        c = load_cohort(code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not c:
        raise HTTPException(404, "No such cohort")
    return c


def _session_codes(programme: str) -> dict[str, list[dict]]:
    """Module code -> its sessions [{code, title}], for every module of the programme (all tracks)."""
    cat = get_catalog()
    prog = cat.programme(programme)
    out: dict[str, list[dict]] = {}
    for mcode in prog.module_codes() if prog else []:
        m = cat.modules.get(mcode)
        if m:
            out[mcode] = [{"code": u.id, "title": u.title} for u in m.units]
    return out


@router.get("/schedule/cohorts")
async def staff_cohorts() -> list[dict]:
    _staff()
    return [
        {"code": c.code, "programme": c.programme, "start": c.start, "sessions": len(c.sessions),
         "members": len(_members(c.code)), "join_code": c.join_code, "join_open": c.join_open}
        for c in list_cohorts()
    ]


@router.get("/schedule/cohorts/{code}")
async def staff_cohort(code: str) -> dict:
    _staff()
    c = _need(code)
    cat = get_catalog()
    modules = [{"code": m, "title": cat.modules[m].title, "sessions": units}
               for m, units in _session_codes(c.programme).items()]
    return {**c.model_dump(), "modules": modules}


@router.put("/schedule/cohorts/{code}")
async def staff_save(code: str, body: Cohort) -> dict:
    _staff()
    if body.code != code:
        raise HTTPException(400, "Cohort code does not match the address")
    if not get_catalog().programme(body.programme):
        raise HTTPException(400, f"Unknown programme {body.programme}")
    known = {u["code"] for units in _session_codes(body.programme).values() for u in units}
    for s in body.sessions:
        if s.code not in known:
            raise HTTPException(400, f"Unknown session {s.code}")
        try:
            starts_at(s)
        except ValueError as exc:
            raise HTTPException(400, f"Bad date or time for {s.code}") from exc
    for d in body.dates:
        try:
            date.fromisoformat(d.date)
        except ValueError as exc:
            raise HTTPException(400, f"Bad date for {d.label}") from exc
    if not body.join_code:
        body.join_code = new_join_code()
    try:
        save_cohort(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return body.model_dump()


class CopyBody(BaseModel):
    to: str
    weeks: int


@router.post("/schedule/cohorts/{code}/copy")
async def staff_copy(code: str, body: CopyBody) -> dict:
    _staff()
    src = _need(code)
    try:
        exists = load_cohort(body.to)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if exists:
        raise HTTPException(409, f"{body.to} already exists")
    new = copy_schedule(src, body.to, body.weeks)
    save_cohort(new)
    return new.model_dump()


@router.get("/schedule/cohorts/{code}/members")
async def staff_members(code: str) -> list[dict]:
    _staff()
    _need(code)
    out = []
    for u in _members(code):
        e = next(e for e in u.enrolments if e.cohort == code)
        out.append({"user_id": u.user_id, "display_name": u.display_name, "track": e.track})
    return sorted(out, key=lambda r: r["display_name"].lower())


class MemberBody(BaseModel):
    cohort: str
    track: str | None = None


@router.put("/schedule/cohorts/{code}/members/{user_id}")
async def staff_set_member(code: str, user_id: str, body: MemberBody) -> dict:
    _staff()
    _need(code)
    target = _need(body.cohort)
    prog = get_catalog().programme(target.programme)
    if body.track and not (prog and prog.track(body.track)):
        raise HTTPException(400, f"No track {body.track}")
    try:
        user = store.load_user(user_id)
    except ValueError as exc:
        raise HTTPException(400, "Bad user") from exc
    e = next((e for e in user.enrolments if e.cohort == code), None)
    if not e:
        raise HTTPException(404, "Not in this cohort")
    e.cohort, e.track, e.programme = target.code, body.track, target.programme
    store.save_user(user)
    return {"ok": True}


# ------------------------------------------------------------------ the learner's week
JOIN_BEFORE = timedelta(minutes=60)  # webinar link shows from an hour before the start ...
JOIN_AFTER = timedelta(hours=3)  # ... until three hours after (the session also stays listed that long)
WEEK = timedelta(days=7)
DATES_AHEAD = timedelta(days=14)
FILES = "/api/yaxa/files/"


def learner_cohort(user: store.YaxaUser) -> Cohort | None:
    for e in user.enrolments:
        if e.cohort:
            try:
                c = load_cohort(e.cohort)
            except ValueError:
                continue
            if c:
                return c
    return None


def week(cu, user: store.YaxaUser, now: datetime | None = None) -> dict:
    """The learner's next seven days: their sessions with prep readings, and key dates."""
    c = learner_cohort(user)
    if not c:
        return {"cohort": None, "sessions": [], "dates": []}
    now = (now or datetime.now(IST)).astimezone(IST)
    cat = get_catalog()
    track = next((e.track for e in user.enrolments if e.cohort == c.code), None)
    modules = [cat.modules[m] for m in _allowed_modules(cat, cu, user) if m in cat.modules]
    home = {u.id: m for m in modules for u in m.units}  # session code -> module
    opened = store.opened(user.user_id)
    groups_cache: dict[str, dict] = {}
    rows = []
    for s in sorted(c.sessions, key=starts_at):
        start = starts_at(s)
        mod = home.get(s.code)
        if not mod or not (now - JOIN_AFTER <= start <= now + WEEK):
            continue
        if mod.code not in groups_cache:
            groups_cache[mod.code] = module_page.module_groups(cat, mod)
        items = groups_cache[mod.code].get(s.code, [])
        unit = next(u for u in mod.units if u.id == s.code)
        rows.append({
            "code": s.code,
            "module": mod.code,
            "module_title": mod.title,
            "title": unit.title,
            "starts_at": start.isoformat(),
            "host": s.host,
            "note": s.note,
            "webinar_url": s.webinar_url if start - JOIN_BEFORE <= now <= start + JOIN_AFTER else "",
            "readings": [
                {"title": r["title"], "open": r["open"],
                 "opened": r["open"].startswith(FILES) and r["open"][len(FILES):] in opened}
                for r in items if r["kind"] != "video"
            ],
            "transcript_ready": any(r["kind"] == "video" and c.code in (r.get("corpus") or "") for r in items),
        })
    today = now.date()
    dates = [
        {"date": d.date, "label": d.label}
        for d in sorted(c.dates, key=lambda d: d.date)
        if (not d.track or d.track == track) and today <= date.fromisoformat(d.date) <= today + DATES_AHEAD
    ]
    return {"cohort": c.code, "sessions": rows, "dates": dates}


@router.get("/schedule/week")
async def my_week() -> dict:
    cu, user = _me()
    return week(cu, user)


# ------------------------------------------------------------------ calendar feed address
FEED = "/api/yaxa-public/calendar/"


def _feed_url(user: store.YaxaUser) -> str:
    if not user.calendar_token:
        user.calendar_token = secrets.token_urlsafe(24)
        store.save_user(user)
    return f"{FEED}{user.calendar_token}.ics"


@router.get("/me/calendar")
async def my_calendar() -> dict:
    _, user = _me()
    return {"url": _feed_url(user)}


@router.post("/me/calendar/reset")
async def reset_calendar() -> dict:
    _, user = _me()
    user.calendar_token = ""
    return {"url": _feed_url(user)}
