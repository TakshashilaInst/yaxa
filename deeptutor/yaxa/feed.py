"""A learner's private calendar feed (iCalendar), for Google Calendar and the like.

Mounted at /api/yaxa-public without login: calendar apps fetch it from their own
servers. The address carries a long random per-learner token instead; the
learner can reset it, which kills the old address. The feed holds session
titles, times and hosts only, never anyone's name or messages.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, HTTPException, Response

from . import store
from .access import _allowed_modules
from .catalog import get_catalog
from .schedule import learner_cohort, starts_at

router = APIRouter()
LENGTH = timedelta(minutes=90)
SITE = "https://yaxa-deeptutor.takshashila.org.in"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines of at most 75 octets, continuations start with a space."""
    out, cur = [], ""
    for ch in line:
        limit = 75 if not out else 74
        if len((cur + ch).encode()) > limit:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


def _local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def ics_for(user: store.YaxaUser, cu_is_admin: bool = False) -> str:
    c = learner_cohort(user)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Takshashila//Yaxa//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_esc((c.code + ' · ') if c else '')}Yaxa", "X-WR-TIMEZONE:Asia/Kolkata"]
    if c:
        cat = get_catalog()
        cu = type("CU", (), {"id": user.user_id, "is_admin": cu_is_admin})()
        mods = [cat.modules[m] for m in _allowed_modules(cat, cu, user) if m in cat.modules]
        home = {u.id: (m, u) for m in mods for u in m.units}
        track = next((e.track for e in user.enrolments if e.cohort == c.code), None)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for s in c.sessions:
            if s.code not in home:
                continue
            mod, unit = home[s.code]
            start = starts_at(s)
            desc = "\n".join(x for x in [f"Host: {s.host}" if s.host else "", s.note,
                                           f"{SITE}/learn/module/{mod.code}#{s.code}"] if x)
            lines += ["BEGIN:VEVENT", f"UID:{c.code}-{s.code}-{s.date}@yaxa", f"DTSTAMP:{stamp}"]
            if s.time:
                lines += [f"DTSTART;TZID=Asia/Kolkata:{_local(start)}", f"DTEND;TZID=Asia/Kolkata:{_local(start + LENGTH)}"]
            else:
                lines += [f"DTSTART;VALUE=DATE:{start:%Y%m%d}"]
            lines += [f"SUMMARY:{_esc(f'{s.code} {unit.title}')}", f"DESCRIPTION:{_esc(desc)}", "END:VEVENT"]
        for i, d in enumerate(c.dates):
            if d.track and d.track != track:
                continue
            day = date.fromisoformat(d.date)
            lines += ["BEGIN:VEVENT", f"UID:{c.code}-date-{d.date}-{i}@yaxa", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                      f"SUMMARY:{_esc(d.label)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(x for line in lines for x in _fold(line)) + "\r\n"


def _user_by_token(token: str) -> store.YaxaUser | None:
    if len(token) < 20:
        return None
    return next((u for u in store.list_users() if u.calendar_token and secrets.compare_digest(u.calendar_token, token)), None)


@router.get("/calendar/{name}")
async def calendar(name: str) -> Response:
    token = name[: -len(".ics")] if name.endswith(".ics") else name
    user = _user_by_token(token)
    if not user:
        raise HTTPException(404, "Not found")
    return Response(ics_for(user), media_type="text/calendar", headers={"Cache-Control": "private, max-age=900"})
