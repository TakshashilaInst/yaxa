"""Cohort life, step 1: cohort schedules, joining by link, the learner's week."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, schedule
from deeptutor.yaxa.schedule import Cohort, KeyDate, Session


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
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
