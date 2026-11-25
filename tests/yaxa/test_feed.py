"""Private calendar feed: a learner's sessions and key dates, for Google Calendar."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, feed, schedule, store
from deeptutor.yaxa.schedule import Cohort, KeyDate, Session


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(
        code="GCPP45", programme="GCPP", join_code="abcDEF1234",
        sessions=[Session(code="CS12", date="2026-11-29", time="11:30", host="Gen. Menon"),
                  Session(code="CT31", date="2026-11-29", time="11:30", host="Nitin Pai")],
        dates=[KeyDate(date="2026-11-28", label="Debate prep, groups of four; bring notes")],
    ))
    user = store.load_user("asha", display_name="Asha Rao")
    user.enrolments = [store.Enrolment(programme="GCPP", track="DFA", cohort="GCPP45")]
    store.save_user(user)
    monkeypatch.setattr(schedule, "_me", lambda: (SimpleNamespace(id="asha", is_admin=False), store.load_user("asha")))
    yield
    catalog.get_catalog(fresh=True)


def _url_token() -> str:
    url = asyncio.run(schedule.my_calendar())["url"]
    assert url.startswith("/api/yaxa-public/calendar/") and url.endswith(".ics")
    return url.rsplit("/", 1)[1][: -len(".ics")]


def test_feed_has_my_sessions_only():
    text = feed.ics_for(store.load_user("asha"))
    assert text.startswith("BEGIN:VCALENDAR")
    assert "SUMMARY:CS12 Tools of Statecraft: Force" in text
    assert "DTSTART;TZID=Asia/Kolkata:20261129T113000" in text and "DTEND;TZID=Asia/Kolkata:20261129T130000" in text
    assert "UID:GCPP45-CS12-2026-11-29@yaxa" in text
    assert "CT31" not in text and "Asha" not in text
    assert "DTSTART;VALUE=DATE:20261128" in text


def test_feed_escapes_and_folds():
    text = feed.ics_for(store.load_user("asha"))
    assert r"Debate prep\, groups of four\; bring notes" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


def test_reset_invalidates_old_token():
    old = _url_token()
    assert _url_token() == old  # stable until reset
    asyncio.run(schedule.reset_calendar())
    with pytest.raises(HTTPException) as e:
        asyncio.run(feed.calendar(f"{old}.ics"))
    assert e.value.status_code == 404


def test_feed_route_needs_no_login():
    token = _url_token()
    resp = asyncio.run(feed.calendar(f"{token}.ics"))
    assert resp.status_code == 200 and resp.media_type == "text/calendar"
    assert resp.body.decode().startswith("BEGIN:VCALENDAR")
