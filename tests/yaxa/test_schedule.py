"""Cohort life, step 1: cohort schedules, joining by link, the learner's week."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, schedule
from deeptutor.yaxa.schedule import Cohort, KeyDate, Session


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    cat = catalog.get_catalog(fresh=True)
    # these tests cover the library-file fallback; pin it rather than depend on the real reading lists
    for mod in cat.modules.values():
        for u in mod.units:
            monkeypatch.setattr(u, "resources", [])
    yield
    catalog.get_catalog(fresh=True)


def _gcpp45(**kw) -> Cohort:
    base = dict(
        code="GCPP45",
        programme="GCPP",
        start="2026-09-06",
        join_code="abcDEF1234",
        sessions=[Session(code="CS12", date="2026-11-29", time="11:30", host="Gen. Menon"),
                  Session(code="CT31", date="2026-11-29", time="11:30", host="Nitin Pai")],
        dates=[KeyDate(date="2026-11-28", label="Final assignment problem statement released")],
    )
    base.update(kw)
    return Cohort(**base)


# ------------------------------------------------------------------ task 1
def test_save_and_load_round_trip():
    c = _gcpp45()
    schedule.save_cohort(c)
    assert schedule.load_cohort("GCPP45") == c
    assert [x.code for x in schedule.list_cohorts()] == ["GCPP45"]


def test_unsafe_cohort_code_rejected():
    with pytest.raises(ValueError):
        schedule.load_cohort("../x")
    with pytest.raises(ValueError):
        schedule.save_cohort(_gcpp45(code="gcpp 45"))


def test_copy_shifts_by_weeks():
    src = _gcpp45()
    new = schedule.copy_schedule(src, "GCPP46", weeks=12)
    assert new.code == "GCPP46" and new.programme == "GCPP"
    assert new.sessions[0].date == "2027-02-21" and new.sessions[0].host == "Gen. Menon"
    assert new.dates[0].date == "2027-02-20"
    assert new.join_code and new.join_code != src.join_code


def test_starts_at_is_ist():
    s = Session(code="CS12", date="2026-11-29", time="11:30")
    assert schedule.starts_at(s).isoformat() == "2026-11-29T11:30:00+05:30"
    assert schedule.starts_at(Session(code="CS12", date="2026-11-29")).isoformat() == "2026-11-29T00:00:00+05:30"


def test_join_code_lookup():
    schedule.save_cohort(_gcpp45())
    assert schedule.cohort_by_join_code("abcDEF1234").code == "GCPP45"
    assert schedule.cohort_by_join_code("nope") is None
    assert len(schedule.new_join_code()) == 10


# ------------------------------------------------------------------ task 2
import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from deeptutor.yaxa import store  # noqa: E402


def _as(monkeypatch, uid: str, *, admin: bool = False, role: str = "student", enrolments=()):
    user = store.load_user(uid, display_name=uid.title())
    user.role = role
    user.enrolments = list(enrolments)
    store.save_user(user)
    cu = SimpleNamespace(id=uid, is_admin=admin)
    monkeypatch.setattr(schedule, "_me", lambda: (cu, store.load_user(uid)))
    return cu


def test_join_enrols_in_programme_and_cohort(monkeypatch):
    schedule.save_cohort(_gcpp45())
    _as(monkeypatch, "asha")
    preview = asyncio.run(schedule.join_preview("abcDEF1234"))
    assert preview["cohort"] == "GCPP45" and preview["open"] and {t["code"] for t in preview["tracks"]} >= {"DFA", "TP"}
    out = asyncio.run(schedule.join("abcDEF1234", schedule.JoinBody(track="DFA")))
    assert out == {"ok": True, "programme": "GCPP", "cohort": "GCPP45", "track": "DFA"}
    assert store.load_user("asha").enrolments == [store.Enrolment(programme="GCPP", track="DFA", cohort="GCPP45")]


def test_join_moves_from_old_cohort_and_keeps_track(monkeypatch):
    schedule.save_cohort(_gcpp45())
    _as(monkeypatch, "ravi", enrolments=[store.Enrolment(programme="GCPP", track="APP", cohort="GCPP44")])
    asyncio.run(schedule.join("abcDEF1234", schedule.JoinBody()))
    assert store.load_user("ravi").enrolments == [store.Enrolment(programme="GCPP", track="APP", cohort="GCPP45")]


def test_closed_or_unknown_code_is_404(monkeypatch):
    schedule.save_cohort(_gcpp45(join_open=False))
    _as(monkeypatch, "asha")
    for code in ("abcDEF1234", "unknown123"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(schedule.join(code, schedule.JoinBody()))
        assert e.value.status_code == 404 and e.value.detail == "This link is no longer open"


def test_bad_track_is_400_and_join_ignores_self_enrol_switch(monkeypatch):
    schedule.save_cohort(_gcpp45())
    _as(monkeypatch, "asha")
    monkeypatch.setattr(catalog.get_catalog().settings, "allow_self_enrol", False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(schedule.join("abcDEF1234", schedule.JoinBody(track="XX")))
    assert e.value.status_code == 400
    assert asyncio.run(schedule.join("abcDEF1234", schedule.JoinBody(track="TP")))["ok"]


# ------------------------------------------------------------------ task 3
def test_staff_only(monkeypatch):
    schedule.save_cohort(_gcpp45())
    _as(monkeypatch, "asha")
    calls = [
        lambda: schedule.staff_cohorts(),
        lambda: schedule.staff_cohort("GCPP45"),
        lambda: schedule.staff_save("GCPP45", _gcpp45()),
        lambda: schedule.staff_copy("GCPP45", schedule.CopyBody(to="GCPP46", weeks=12)),
        lambda: schedule.staff_members("GCPP45"),
        lambda: schedule.staff_set_member("GCPP45", "asha", schedule.MemberBody(cohort="GCPP45")),
    ]
    for call in calls:
        with pytest.raises(HTTPException) as e:
            asyncio.run(call())
        assert e.value.status_code == 403


def test_put_generates_join_code_and_lists(monkeypatch):
    _as(monkeypatch, "staff", admin=True)
    saved = asyncio.run(schedule.staff_save("GCPP45", _gcpp45(join_code="")))
    assert len(saved["join_code"]) == 10
    rows = asyncio.run(schedule.staff_cohorts())
    assert rows[0]["code"] == "GCPP45" and rows[0]["sessions"] == 2 and rows[0]["members"] == 0
    view = asyncio.run(schedule.staff_cohort("GCPP45"))
    dfa = next(m for m in view["modules"] if m["code"] == "DFA-AS")
    assert {"code": "CS22", "title": dfa["sessions"][1]["title"]} in dfa["sessions"]


def test_session_code_must_belong_to_programme(monkeypatch):
    _as(monkeypatch, "staff", admin=True)
    bad = _gcpp45(sessions=[Session(code="CS99", date="2026-11-29")])
    with pytest.raises(HTTPException) as e:
        asyncio.run(schedule.staff_save("GCPP45", bad))
    assert e.value.status_code == 400 and e.value.detail == "Unknown session CS99"
    with pytest.raises(HTTPException):
        asyncio.run(schedule.staff_save("GCPP46", _gcpp45()))  # body code must match the path


def test_copy_creates_next_cohort(monkeypatch):
    _as(monkeypatch, "staff", admin=True)
    asyncio.run(schedule.staff_save("GCPP45", _gcpp45()))
    asyncio.run(schedule.staff_copy("GCPP45", schedule.CopyBody(to="GCPP46", weeks=12)))
    assert schedule.load_cohort("GCPP46").sessions[0].date == "2027-02-21"


def test_members_lists_enrolled_users_and_sets_track(monkeypatch):
    schedule.save_cohort(_gcpp45())
    schedule.save_cohort(_gcpp45(code="GCPP46", join_code="zzzzzzzzzz"))
    _as(monkeypatch, "asha", enrolments=[store.Enrolment(programme="GCPP", cohort="GCPP45")])
    _as(monkeypatch, "staff", admin=True)
    members = asyncio.run(schedule.staff_members("GCPP45"))
    assert members == [{"user_id": "asha", "display_name": "Asha", "track": None}]
    asyncio.run(schedule.staff_set_member("GCPP45", "asha", schedule.MemberBody(track="DFA", cohort="GCPP46")))
    assert store.load_user("asha").enrolments == [store.Enrolment(programme="GCPP", track="DFA", cohort="GCPP46")]


# ------------------------------------------------------------------ task 4
from datetime import datetime, timedelta  # noqa: E402

from deeptutor.yaxa import module_page  # noqa: E402
from deeptutor.yaxa.catalog import SourceInfo  # noqa: E402

IST = schedule.IST
CS12_FILES = {
    "CS12 - a.pdf": SourceInfo(title="CS12 Windows of War", kind="pdf", unit="CS12", module="DFA-SSIR"),
    "CS12 - b.pdf": SourceInfo(title="CS12 Another Bloody Century", kind="pdf", unit="CS12", module="DFA-SSIR"),
    "Webinar - CS12.md": SourceInfo(title="Webinar: CS12 Force, Prakash Menon", kind="video", unit="CS12",
                                    module="DFA-SSIR", corpus="Webinar recording, GCPP45 (Nov 2026)"),
}


def _asha(monkeypatch, files=CS12_FILES):
    monkeypatch.setattr(module_page, "_files", lambda kb: dict(files) if kb == "DFA" else {})
    cu = _as(monkeypatch, "asha", enrolments=[store.Enrolment(programme="GCPP", track="DFA", cohort="GCPP45")])
    return cu, store.load_user("asha")


def test_week_shows_only_my_track_and_window(monkeypatch):
    schedule.save_cohort(_gcpp45(sessions=[
        Session(code="CS12", date="2026-11-29", time="11:30", host="Gen. Menon", webinar_url="https://zoom/x"),
        Session(code="CT31", date="2026-11-29", time="11:30"),
        Session(code="CS13", date="2026-12-06", time="11:30"),
    ]))
    cu, user = _asha(monkeypatch)
    w = schedule.week(cu, user, now=datetime(2026, 11, 25, 10, 0, tzinfo=IST))
    assert w["cohort"] == "GCPP45"
    assert [s["code"] for s in w["sessions"]] == ["CS12"]
    row = w["sessions"][0]
    assert row["module"] == "DFA-SSIR" and row["starts_at"] == "2026-11-29T11:30:00+05:30" and row["host"] == "Gen. Menon"
    assert [r["title"] for r in row["readings"]] == ["CS12 Another Bloody Century", "CS12 Windows of War"]
    assert row["transcript_ready"] is True
    assert [d["label"] for d in w["dates"]] == ["Final assignment problem statement released"]


def test_week_ist_boundary(monkeypatch):
    schedule.save_cohort(_gcpp45(sessions=[Session(code="CS12", date="2026-12-07", time="09:00")]))
    cu, user = _asha(monkeypatch)
    w = schedule.week(cu, user, now=datetime(2026, 11, 30, 23, 30, tzinfo=IST))  # 18:00 UTC, still Sunday in UTC terms
    assert [s["starts_at"] for s in w["sessions"]] == ["2026-12-07T09:00:00+05:30"]


def test_webinar_link_only_in_window(monkeypatch):
    schedule.save_cohort(_gcpp45(sessions=[Session(code="CS12", date="2026-11-29", time="11:30", webinar_url="https://zoom/x")]))
    cu, user = _asha(monkeypatch)
    start = datetime(2026, 11, 29, 11, 30, tzinfo=IST)
    assert schedule.week(cu, user, now=start - timedelta(hours=2))["sessions"][0]["webinar_url"] == ""
    assert schedule.week(cu, user, now=start - timedelta(minutes=30))["sessions"][0]["webinar_url"] == "https://zoom/x"
    assert schedule.week(cu, user, now=start + timedelta(hours=4))["sessions"] == []


def test_no_cohort_returns_empty(monkeypatch):
    cu = _as(monkeypatch, "ravi", enrolments=[store.Enrolment(programme="GCPP", track="APP")])
    assert schedule.week(cu, store.load_user("ravi")) == {"cohort": None, "sessions": [], "dates": []}


def test_opened_ticks(monkeypatch):
    schedule.save_cohort(_gcpp45())
    cu, user = _asha(monkeypatch)
    store.mark_opened("asha", "DFA", "CS12 - a.pdf")
    row = schedule.week(cu, user, now=datetime(2026, 11, 25, 10, 0, tzinfo=IST))["sessions"][0]
    assert {r["title"]: r["opened"] for r in row["readings"]} == {"CS12 Windows of War": True, "CS12 Another Bloody Century": False}


def test_week_rows_carry_learn_and_check(monkeypatch):
    from deeptutor.yaxa import cases

    schedule.save_cohort(_gcpp45(sessions=[Session(code="CS12", date="2026-11-29", time="11:30")]))
    cu, user = _asha(monkeypatch)
    row = schedule.week(cu, user, now=datetime(2026, 11, 25, 10, 0, tzinfo=IST))["sessions"][0]
    assert row["learn"] == {"case": False, "status": "not_started", "conversation_id": None}
    assert row["check"]["available"] is False
    assert row["layer"] == {"available": False, "written": False}
    cases.save_case(cases.Case(module="DFA-SSIR", session="CS12", status="approved", title="t", situation="w " * 100,
                               opening="o?", grasp=["a", "b"]))
    row = schedule.week(cu, user, now=datetime(2026, 11, 25, 10, 0, tzinfo=IST))["sessions"][0]
    assert row["learn"]["case"] is True and row["learn"]["status"] == "not_started"
