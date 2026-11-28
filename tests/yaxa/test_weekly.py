"""Weekly emails: the Sunday nudge to a cohort's email groups and the Friday note to faculty."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, mailer, schedule, store, weekly
from deeptutor.yaxa.schedule import Cohort, Session

SUN = date(2026, 11, 29)


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP", email_group="gcpp45@example.org",
                                faculty_email_group="gcpp-faculty@example.org", weekly_email=True, sessions=[
        Session(code="CP11", date="2026-12-05", time="09:30", host="Ameya Naik"),
        Session(code="CP12", date="2026-12-12"),  # next week: not in this email
    ]))
    store.save_user(store.load_user("asha", display_name="Asha"))
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append((to, subject, text)))
    monkeypatch.setattr(weekly, "_today", lambda: SUN)
    yield sent
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, admin=False):
    monkeypatch.setattr(weekly, "_me", lambda: (SimpleNamespace(id=uid, is_admin=admin), store.load_user(uid)))


def test_sunday_lists_this_weeks_sessions_only():
    mails = weekly.compose("sunday", schedule.load_cohort("GCPP45"))
    assert [m["to"] for m in mails] == ["gcpp45@example.org"]
    text = mails[0]["text"]
    assert "CP11" in text and "CP12" not in text and "Ameya Naik" in text
    assert "/learn" in text


def test_track_groups_get_their_own_mail():
    c = schedule.load_cohort("GCPP45")
    c.track_email_groups = {"TP": "gcpp45-tp@example.org"}
    schedule.save_cohort(c)
    assert [m["to"] for m in weekly.compose("sunday", schedule.load_cohort("GCPP45"))] == ["gcpp45-tp@example.org"]


def test_no_sessions_this_week_means_no_mail():
    c = schedule.load_cohort("GCPP45")
    c.sessions = [Session(code="CP12", date="2026-12-12")]
    assert weekly.compose("sunday", c) == []


def test_friday_goes_to_faculty_group():
    mails = weekly.compose("friday", schedule.load_cohort("GCPP45"))
    assert [m["to"] for m in mails] == ["gcpp-faculty@example.org"]
    assert "/learn/faculty" in mails[0]["text"]


def test_run_sends_once_per_day_and_skips_cohorts_switched_off(_tmp_home):
    sent = _tmp_home
    weekly.run("sunday")
    weekly.run("sunday")
    assert len(sent) == 1
    c = schedule.load_cohort("GCPP45")
    c.weekly_email = False
    schedule.save_cohort(c)
    weekly.run("sunday", today=date(2026, 12, 6))
    assert len(sent) == 1


def test_staff_send_a_test_to_one_address(monkeypatch, _tmp_home):
    sent = _tmp_home
    as_(monkeypatch, "root", admin=True)
    out = asyncio.run(weekly.send_test("GCPP45", weekly.TestBody(kind="sunday", to="pranay@example.org")))
    assert out["sent"] == 1 and sent[0][0] == "pranay@example.org" and sent[0][1].startswith("[Test] ")


def test_students_cannot_preview(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException):
        asyncio.run(weekly.preview("GCPP45", "sunday"))
