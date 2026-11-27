"""Spaced review: each unit's next review date, rebuilt from practice history with DeepTutor's scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, practice, review, store

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
DAY = 86400


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield
    catalog.get_catalog(fresh=True)


def _item(unit: str, score: int | None, day: float, module: str = "GCPP-ER1", user: str = "u_r") -> store.PracticeItem:
    at = (T0 + timedelta(days=day)).isoformat()
    return store.PracticeItem(user_id=user, module=module, unit=unit, question="q", score=score, answered_at=at if score is not None else "", created_at=at)


def test_unanswered_unit_has_no_schedule():
    assert review.schedule([]) is None
    assert review.schedule([_item("U1", None, 0)]) is None


def test_weak_answer_comes_back_sooner_than_full_marks():
    weak = review.schedule([_item("U1", 0, 0)])
    strong = review.schedule([_item("U1", 3, 0)])
    assert weak.next_review_at < strong.next_review_at
    assert strong.next_review_at > T0.timestamp() + 2 * DAY  # full marks: not before ~3 days


def test_spaced_full_marks_push_the_next_review_further_out():
    once = review.schedule([_item("U1", 3, 0)])
    twice = review.schedule([_item("U1", 3, 0), _item("U1", 3, 5)])
    gap_once = once.next_review_at - T0.timestamp()
    gap_twice = twice.next_review_at - (T0.timestamp() + 5 * DAY)
    assert gap_twice > gap_once


def test_answers_are_replayed_in_time_order_not_file_order():
    a = review.schedule([_item("U1", 3, 0), _item("U1", 0, 4)])
    b = review.schedule([_item("U1", 0, 4), _item("U1", 3, 0)])
    assert a.next_review_at == b.next_review_at


def test_unit_review_reports_due_and_recall():
    items = [_item("U1", 3, 0)]
    state = review.schedule(items)
    before = review.unit_review(items, now=state.next_review_at - DAY)
    after = review.unit_review(items, now=state.next_review_at + DAY)
    assert before["due"] is False and after["due"] is True
    assert 0 < after["recall"] < before["recall"] <= 1
    assert before["next_review"] == datetime.fromtimestamp(state.next_review_at, timezone.utc).date().isoformat()
    assert review.unit_review([], now=T0.timestamp()) is None


def test_due_units_lists_only_due_units_most_overdue_first():
    mod = catalog.get_catalog().module("GCPP-ER1")
    u1, u2, u3 = (u.id for u in mod.units[:3])
    store.save_practice(_item(u1, 3, 0))
    store.save_practice(_item(u2, 0, 0))
    store.save_practice(_item(u3, 3, 30))  # recent: not due
    now = T0.timestamp() + 20 * DAY
    due = review.due_units("u_r", [mod], now=now)
    assert [d["unit"] for d in due] == [u2, u1]
    assert due[0]["module"] == "GCPP-ER1" and due[0]["unit_title"] == mod.units[1].title
    assert due[0]["days_overdue"] >= due[1]["days_overdue"]


def test_due_units_ignore_other_students_and_other_modules():
    er1 = catalog.get_catalog().module("GCPP-ER1")
    store.save_practice(_item(er1.units[0].id, 0, 0, user="someone_else"))
    store.save_practice(_item("X1", 0, 0, module="GCPP-Fundamentals"))
    assert review.due_units("u_r", [er1], now=T0.timestamp() + 30 * DAY) == []


def test_progress_rows_carry_review_fields_and_due_units_are_picked_first():
    mod = catalog.get_catalog().module("GCPP-ER1")
    first, second = mod.units[0].id, mod.units[1].id
    store.save_practice(_item(first, 3, -200))
    store.save_practice(_item(first, 3, -180))  # mastered, but long ago: due again
    rows = {r["id"]: r for r in practice._progress("u_r", mod)}
    assert rows[first]["status"] == "mastered"
    assert rows[first]["review"]["due"] is True
    assert rows[second]["review"] is None
    assert practice._pick_unit(mod, list(rows.values()), None).id == first
