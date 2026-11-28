"""Prepare next week: each upcoming session's case, layer and check status, and drafting what's missing."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import cases, catalog, checks, layers, prepare, schedule, store
from deeptutor.yaxa.schedule import Cohort, Session


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP", sessions=[
        Session(code="CP10", date="2026-11-21"),  # last week: past
        Session(code="CP11", date="2026-11-28"),
        Session(code="CP12", date="2026-12-05"),
        Session(code="CP13", date="2026-12-26"),  # beyond two weeks
    ]))
    store.save_user(store.load_user("asha", display_name="Asha"))
    monkeypatch.setattr(prepare, "_today", lambda: date(2026, 11, 24))
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, admin=False):
    monkeypatch.setattr(prepare, "_me", lambda: (SimpleNamespace(id=uid, is_admin=admin, username=uid), store.load_user(uid)))


def test_lists_the_next_two_weeks_with_status(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    cases.save_case(cases.Case(module="GCPP-Fundamentals", session="CP11", title="t", situation="s", opening="o", grasp=["g"]))
    rows = asyncio.run(prepare.upcoming("GCPP45"))["sessions"]
    assert [r["session"] for r in rows] == ["CP11", "CP12"]
    cp11 = rows[0]
    assert cp11["module"] == "GCPP-Fundamentals" and cp11["date"] == "2026-11-28"
    assert cp11["case"] == "draft" and cp11["layer"] == "none" and cp11["check"] == "none"
    assert cp11["after"] == "none"


def test_all_weeks_includes_past_and_later(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    rows = asyncio.run(prepare.upcoming("GCPP45", all_weeks=True))["sessions"]
    assert [r["session"] for r in rows] == ["CP10", "CP11", "CP12", "CP13"]


def test_draft_missing_drafts_only_what_is_missing(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    made = []

    async def fake_case(cu, user, m, s):
        made.append("case")
        return cases.Case(module=m, session=s, title="t", situation="s", opening="o", grasp=["g"])

    async def fake_layer(cu, user, m, s):
        made.append("layer")
        return layers.Layer(module=m, session=s, prompt="do it", self_check=["a", "b", "c"])

    async def fake_qs(cu, user, m, s, n, avoid):
        made.append("check")
        return []

    monkeypatch.setattr(cases, "_draft_case", fake_case)
    monkeypatch.setattr(layers, "_draft", fake_layer)
    monkeypatch.setattr(checks, "_draft_questions", fake_qs)
    cases.save_case(cases.Case(module="GCPP-Fundamentals", session="CP11", title="mine", situation="s", opening="o", grasp=["g"]))
    out = asyncio.run(prepare.draft_missing("GCPP-Fundamentals", "CP11"))
    assert sorted(made) == ["check", "layer"]
    assert out["case"] == "draft" and out["layer"] == "draft" and out["check"] == "draft"
    assert cases.load_case("GCPP-Fundamentals", "CP11").title == "mine"  # existing work untouched


def test_one_failed_draft_does_not_lose_the_others(monkeypatch):
    as_(monkeypatch, "root", admin=True)

    async def boom(*a, **k):
        raise HTTPException(503, "model down")

    async def fake_case(cu, user, m, s):
        return cases.Case(module=m, session=s, title="t", situation="s", opening="o", grasp=["g"])

    monkeypatch.setattr(cases, "_draft_case", fake_case)
    monkeypatch.setattr(layers, "_draft", boom)
    monkeypatch.setattr(checks, "_draft_questions", boom)
    out = asyncio.run(prepare.draft_missing("GCPP-Fundamentals", "CP11"))
    assert out["case"] == "draft" and out["layer"] == "none"
    assert out["errors"] and "model down" in " ".join(out["errors"])


def test_students_cannot_prepare(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(prepare.upcoming("GCPP45"))
    assert e.value.status_code == 403
