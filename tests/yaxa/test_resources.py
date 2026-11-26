"""Session reading lists in Yaxa (mandatory, recommended, self-assessment), so learners
no longer need the OpenTakshashila session page."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.yaxa import catalog, module_page, schedule, store
from deeptutor.yaxa.catalog import Resource, SourceInfo

FILES = {
    "CS12 - Windows of War.pdf": SourceInfo(title="CS12 Windows of War", kind="pdf", unit="CS12", module="DFA-SSIR"),
    "CS12 - Extra library item.pdf": SourceInfo(title="CS12 Extra library item", kind="pdf", unit="CS12", module="DFA-SSIR"),
}
RESOURCES = [
    Resource(kind="recommended", title="On War", url="https://example.org/on-war", note="Clausewitz, book I"),
    Resource(kind="mandatory", title="Windows of War", url="https://media2-production.mightynetworks.com/asset/x/w.pdf",
             file="CS12 - Windows of War.pdf", note="Essay by a strategist"),
    Resource(kind="mandatory", title="Why deterrence works", url="https://youtu.be/abc", note="A short video"),
    Resource(kind="self_assessment", title="Self-assessment quiz", file="CS12 - Self-assessment.pdf"),
]


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    cat = catalog.get_catalog(fresh=True)
    unit = next(u for u in cat.modules["DFA-SSIR"].units if u.id == "CS12")
    monkeypatch.setattr(unit, "resources", list(RESOURCES))
    monkeypatch.setattr(module_page, "_files", lambda kb: dict(FILES) if kb == "DFA" else {})
    u = store.load_user("asha", display_name="Asha")
    u.enrolments = [store.Enrolment(programme="GCPP", track="DFA", cohort="GCPP45")]
    store.save_user(u)
    cu = SimpleNamespace(id="asha", is_admin=False)
    monkeypatch.setattr(module_page, "_me", lambda: (cu, store.load_user("asha")))
    monkeypatch.setattr(schedule, "_me", lambda: (cu, store.load_user("asha")))
    yield
    catalog.get_catalog(fresh=True)


def _cs12():
    return next(u for u in asyncio.run(module_page.module_view("DFA-SSIR"))["units"] if u["id"] == "CS12")


def test_module_page_lists_mandatory_then_recommended_and_no_lms_link():
    u = _cs12()
    assert "lms_url" not in u
    assert [(r["kind"], r["title"]) for r in u["resources"]] == [
        ("mandatory", "Windows of War"), ("mandatory", "Why deterrence works"),
        ("recommended", "On War"), ("self_assessment", "Self-assessment quiz"),
    ]
    by = {r["title"]: r for r in u["resources"]}
    assert by["Windows of War"]["open"] == "/api/yaxa/files/DFA/CS12 - Windows of War.pdf"  # our library copy, not Mighty
    assert by["Windows of War"]["in_library"] is True and by["Windows of War"]["note"] == "Essay by a strategist"
    assert by["Why deterrence works"]["open"] == "https://youtu.be/abc" and by["Why deterrence works"]["in_library"] is False


def test_library_copy_is_not_listed_twice():
    u = _cs12()
    assert [r["title"] for r in u["readings"]] == ["CS12 Extra library item"]


def test_resource_whose_library_file_is_missing_falls_back_to_its_link():
    u = _cs12()
    quiz = next(r for r in u["resources"] if r["kind"] == "self_assessment")
    assert quiz["open"] == "" and quiz["in_library"] is False  # file not synced yet, no link: shown without a link


def test_week_counts_only_mandatory_and_ticks_web_links():
    schedule.save_cohort(schedule.Cohort(code="GCPP45", programme="GCPP",
                                         sessions=[schedule.Session(code="CS12", date="2026-11-29", time="11:30")]))
    asyncio.run(schedule.mark_link_opened(schedule.OpenedBody(url="https://youtu.be/abc")))
    user = store.load_user("asha")
    w = schedule.week(SimpleNamespace(id="asha", is_admin=False), user, now=datetime(2026, 11, 26, 9, 0, tzinfo=schedule.IST))
    rows = w["sessions"][0]["readings"]
    assert [(r["title"], r["opened"]) for r in rows] == [("Windows of War", False), ("Why deterrence works", True)]


def test_opening_our_copy_ticks_it(monkeypatch):
    store.mark_opened("asha", "DFA", "CS12 - Windows of War.pdf")
    assert next(r for r in _cs12()["resources"] if r["title"] == "Windows of War")["opened"] is True


def test_opened_rejects_non_links():
    with pytest.raises(Exception):
        asyncio.run(schedule.mark_link_opened(schedule.OpenedBody(url="javascript:alert(1)")))


def test_unit_row_carries_check_status():
    from deeptutor.yaxa import checks, community

    assert _cs12()["check"] == {"available": False, "best": None, "ready": False, "attempts": 0}
    qs = [checks.Question(id=f"q{i}", text=f"Q{i}?", options=[
        checks.Option(text="r", correct=True, why="w"), checks.Option(text="x", why="w", misconception="m"),
        checks.Option(text="y", why="w", misconception="n")]) for i in range(1, 6)]
    checks.save_set(checks.CheckSet(module="DFA-SSIR", session="CS12", status="approved", questions=qs))
    community.append_jsonl(checks._attempts_path("_none", "DFA-SSIR", "CS12"),
                           {"user_id": "asha", "version": 1, "answer_version": 1, "answers": {}, "score": 4,
                            "first": True, "staff": False, "at": "x"})
    assert _cs12()["check"] == {"available": True, "best": 4, "ready": True, "attempts": 1}
