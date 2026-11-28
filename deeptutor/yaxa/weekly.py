"""Weekly emails, sent by a systemd timer (``python -m deeptutor.yaxa.weekly sunday|friday``).

- Sunday: to each cohort's email group (or each track's group, when set), the sessions in the
  week ahead, with their readings and session check.
- Friday: to the cohort's faculty group, the week's sessions, class questions waiting, and
  a link to the cohort brief.

Only cohorts with ``weekly_email`` on, not closed, get mail; each address gets each kind at most
once a day. Plain text, no tracking. Staff can preview and send themselves a test first.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import sys
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import checks, discussion, mailer, store
from .access import _me, _privileged
from .announcements import SITE
from .catalog import get_catalog
from .schedule import Cohort, list_cohorts, load_cohort

log = logging.getLogger(__name__)
router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
KINDS = ("sunday", "friday")


def _today() -> date:
    return datetime.now(IST).date()


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a %-d %b")


def _module_of(session: str):
    for m in get_catalog().modules.values():
        for u in m.units:
            if u.id == session:
                return m, u
    return None, None


def _week(c: Cohort, today: date) -> list[Any]:
    """Sessions from today through the next six days."""
    end = (today + timedelta(days=7)).isoformat()
    return [s for s in sorted(c.sessions, key=lambda s: (s.date, s.time)) if today.isoformat() <= s.date < end]


def _session_block(s) -> str:
    m, u = _module_of(s.code)
    if not m:
        return ""
    when = _day(s.date) + (f", {s.time}" if s.time else "") + (f", with {s.host}" if s.host else "")
    lines = [f"{s.code} · {u.title} ({when})"]
    chk = checks.load_set(m.code, s.code)
    if chk and chk.status == "approved":
        lines.append("  Before Saturday: take the session check.")
    lines.append(f"  Readings and Ask Yaxa: {SITE}/learn/module/{m.code}#{s.code}")
    return "\n".join(lines)


def _sunday(c: Cohort, today: date) -> list[dict[str, str]]:
    week = _week(c, today)
    if not week:
        return []
    prog = get_catalog().programme(c.programme)
    targets: list[tuple[str, list[str] | None]] = []
    if c.track_email_groups:
        targets = [(g, prog.module_codes(t) if prog else None) for t, g in c.track_email_groups.items() if g]
    elif c.email_group:
        targets = [(c.email_group, None)]
    out = []
    for to, modules in targets:
        blocks = [b for s in week if (modules is None or (_module_of(s.code)[0] and _module_of(s.code)[0].code in modules))
                  for b in [_session_block(s)] if b]
        if not blocks:
            continue
        sat = max(s.date for s in week)
        text = (f"Hello,\n\nYour week in Yaxa, ahead of the live session on {_day(sat)}.\n\n" + "\n\n".join(blocks)
                + f"\n\nOpen this week: {SITE}/learn\n\n— Takshashila\n")
        subject = f"[{c.code}] This week: " + ", ".join(s.code for s in week)
        out.append({"to": to, "subject": subject, "text": text})
    return out


def _waiting(cohort: str) -> int:
    n = 0
    for f in sorted(discussion._dir(cohort).glob("*.json")):
        n += sum(1 for t in store._read_json(f) or [] if not t.get("hidden") and discussion._needs_faculty(t))
    return n


def _friday(c: Cohort, today: date) -> list[dict[str, str]]:
    if not c.faculty_email_group:
        return []
    week = _week(c, today)
    if not week:
        return []
    lines = [f"{s.code} · {(_module_of(s.code)[1].title if _module_of(s.code)[1] else '')} ({_day(s.date)})" for s in week]
    text = ("Hello,\n\nAhead of Saturday's sessions:\n\n" + "\n".join(lines)
            + f"\n\nClass questions waiting for faculty: {_waiting(c.code)} — {SITE}/learn/faculty/discussion"
            + f"\nThe cohort brief: {SITE}/learn/faculty\n\n— Yaxa\n")
    return [{"to": c.faculty_email_group, "subject": f"[{c.code}] Friday note for faculty", "text": text}]


def compose(kind: str, c: Cohort, today: date | None = None) -> list[dict[str, str]]:
    today = today or _today()
    return _sunday(c, today) if kind == "sunday" else _friday(c, today)


# ------------------------------------------------------------------ sending
def _log_path():
    return store.yaxa_root() / "mail-log.json"


def run(kind: str, today: date | None = None, dry_run: bool = False) -> list[dict[str, str]]:
    """Send this kind's mail for every switched-on cohort; returns what was (or would be) sent."""
    today = today or _today()
    sent_log = store._read_json(_log_path()) or {}
    done = []
    for c in list_cohorts():
        if not c.weekly_email or c.closed:
            continue
        for m in compose(kind, c, today):
            key = f"{kind}:{c.code}:{m['to']}:{today.isoformat()}"
            if key in sent_log:
                continue
            if not dry_run:
                try:
                    mailer.send(m["to"], m["subject"], m["text"])
                except Exception:  # noqa: BLE001 - one bad group must not stop the others
                    log.exception("weekly %s mail to %s failed", kind, m["to"])
                    continue
                sent_log[key] = datetime.now(IST).isoformat()
            done.append(m)
    if not dry_run:
        store._write_json(_log_path(), sent_log)
    return done


# ------------------------------------------------------------------ staff: preview and test
class TestBody(BaseModel):
    kind: str
    to: str


def _staff():
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Faculty and staff only")
    return cu, user


def _cohort(code: str) -> Cohort:
    try:
        c = load_cohort(code)
    except ValueError:
        c = None
    if not c:
        raise HTTPException(404, "No such cohort")
    return c


@router.get("/weekly/{cohort}/{kind}")
async def preview(cohort: str, kind: str) -> dict[str, Any]:
    _staff()
    if kind not in KINDS:
        raise HTTPException(400, "kind is sunday or friday")
    c = _cohort(cohort)
    return {"enabled": c.weekly_email, "configured": mailer.configured(), "mails": compose(kind, c)}


@router.post("/weekly/{cohort}/test")
async def send_test(cohort: str, body: TestBody) -> dict[str, Any]:
    _staff()
    if body.kind not in KINDS:
        raise HTTPException(400, "kind is sunday or friday")
    to = body.to.strip()
    if "@" not in to or " " in to:
        raise HTTPException(400, "Give one email address")
    if not mailer.configured():
        raise HTTPException(409, "Email is not set up on the server yet")
    mails = compose(body.kind, _cohort(cohort))
    if not mails:
        raise HTTPException(409, "Nothing to send this week for this cohort")
    for m in mails:
        mailer.send(to, f"[Test] {m['subject']} (would go to {m['to']})", m["text"])
    return {"sent": len(mails)}


if __name__ == "__main__":  # pragma: no cover - run by the systemd timer
    logging.basicConfig(level=logging.INFO)
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in KINDS:
        sys.exit("usage: python -m deeptutor.yaxa.weekly sunday|friday [--dry-run]")
    for m in run(kind, dry_run="--dry-run" in sys.argv):
        print(f"{'would send' if '--dry-run' in sys.argv else 'sent'} {kind} to {m['to']}: {m['subject']}")
