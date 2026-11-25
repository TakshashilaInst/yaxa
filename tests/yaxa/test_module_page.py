"""Module page: a module's units with their readings, recordings and the student's progress."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import access, catalog, module_page, practice, store
from deeptutor.yaxa.catalog import Module, SourceInfo, Unit


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield
    catalog.get_catalog(fresh=True)


def _mod(code: str = "TP-IE", kb: str = "TP") -> Module:
    return Module(
        code=code,
        title="Information Economics",
        kb=kb,
        units=[
            Unit(id="U01", title="Nature and Pricing of Information Goods"),
            Unit(id="U02", title="Switching Costs and Lock-In"),
            Unit(id="U03", title="Network Effects"),
        ],
    )


def _titles(groups: dict, key: str) -> list[str]:
    return [r["title"] for r in groups[key]]


def test_readings_match_units_by_id_then_title_and_others_go_last():
    files = {
        "a.pdf": SourceInfo(title="A reading", unit="U02", module="TP-IE"),
        "CT31 - b.pdf": SourceInfo(title="CT31 Nature and Pricing of Information Goods: Capitalism Without Capital", unit="CT31", module="TP-IE"),
        "c.pdf": SourceInfo(title="Something general", module="TP-IE"),
    }
    groups = module_page.group_readings(_mod(), files, shared_kb=True)
    assert _titles(groups, "U02") == ["A reading"]
    assert _titles(groups, "U01") == ["CT31 Nature and Pricing of Information Goods: Capitalism Without Capital"]
    assert _titles(groups, "other") == ["Something general"]


def test_session_codes_map_to_units_in_order_when_counts_match():
    files = {
        "x.pdf": SourceInfo(title="Farrell on coordination", unit="CT33", module="TP-IE"),
        "y.pdf": SourceInfo(title="Stiglitz on information", unit="CT31", module="TP-IE"),
        "z.pdf": SourceInfo(title="Katz and Shapiro", unit="CT34", module="TP-IE"),
    }
    groups = module_page.group_readings(_mod(), files, shared_kb=True)
    assert _titles(groups, "U01") == ["Stiglitz on information"]
    assert _titles(groups, "U02") == ["Farrell on coordination"]
    assert _titles(groups, "U03") == ["Katz and Shapiro"]


def test_retired_files_and_other_modules_files_are_left_out():
    files = {
        "old.pdf": SourceInfo(title="Old", unit="U01", module="TP-IE", retired=True),
        "ai.pdf": SourceInfo(title="AI reading", unit="U01", module="TP-AI"),
        "untagged.pdf": SourceInfo(title="Untagged in a shared library"),
    }
    groups = module_page.group_readings(_mod(), files, shared_kb=True)
    assert all(not v for v in groups.values())
    # a library used by one module only keeps its untagged files
    solo = module_page.group_readings(_mod("GCPP-ER1", "GCPP-ER1"), {"u.pdf": SourceInfo(title="Untagged")}, shared_kb=False)
    assert _titles(solo, "other") == ["Untagged"]


def test_reading_links_open_inside_yaxa_and_recordings_offer_the_transcript():
    files = {
        "r.pdf": SourceInfo(title="Paper", kind="pdf", unit="U01"),
        "Webinar - CP21.md": SourceInfo(title="Webinar: CP21", kind="video", unit="U01",
                                        url="https://drive.google.com/file/d/abc/view", corpus="Webinar recording, GCPP44"),
        "op-ed.md": SourceInfo(title="An op-ed", kind="note", unit="U01", url="https://theprint.in/x"),
    }
    groups = module_page.group_readings(_mod("GCPP-ER1", "GCPP-ER1"), files, shared_kb=False)
    by_title = {r["title"]: r for r in groups["U01"]}
    assert by_title["Paper"]["open"] == "/api/yaxa/files/GCPP-ER1/r.pdf"
    assert by_title["Webinar: CP21"]["kind"] == "video"
    assert by_title["Webinar: CP21"]["open"] == "/api/yaxa/files/GCPP-ER1/Webinar - CP21.md"
    assert "drive.google.com" not in str(by_title["Webinar: CP21"])  # staff-only Drive library: never linked
    assert by_title["An op-ed"]["open"] == "https://theprint.in/x"


def _student() -> tuple[SimpleNamespace, store.YaxaUser]:
    user = store.load_user("s1", display_name="Student")
    user.enrolments = [store.Enrolment(programme="GCPP", track="TP")]
    return SimpleNamespace(id="s1", is_admin=False), user


def test_module_view_requires_access_and_carries_progress(monkeypatch):
    cu, user = _student()
    monkeypatch.setattr(module_page, "_me", lambda: (cu, user))
    monkeypatch.setattr(module_page, "_files", lambda kb: {})
    cat = catalog.get_catalog()
    allowed = access._allowed_modules(cat, cu, user)
    code = next(c for c in allowed if cat.modules[c].units)
    unit = cat.modules[code].units[0].id
    store.save_practice(store.PracticeItem(user_id="s1", module=code, unit=unit, question="q", score=3,
                                           answered_at="2026-11-01T09:00:00+00:00"))
    view = asyncio.run(module_page.module_view(code))
    first = view["units"][0]
    assert first["id"] == unit and first["progress"]["status"] == "practising" and first["progress"]["review"]
    outside = next(c for c, m in cat.modules.items() if c not in allowed and m.available)
    with pytest.raises(HTTPException) as e:
        asyncio.run(module_page.module_view(outside))
    assert e.value.status_code == 403


def test_practice_summary_counts_per_module(monkeypatch):
    cu, user = _student()
    monkeypatch.setattr(practice, "_me", lambda: (cu, user))
    cat = catalog.get_catalog()
    code = next(c for c in access._allowed_modules(cat, cu, user) if cat.modules[c].units)
    unit = cat.modules[code].units[0].id
    for day in (1, 2):
        store.save_practice(store.PracticeItem(user_id="s1", module=code, unit=unit, question="q", score=3,
                                               answered_at=f"2026-11-0{day}T09:00:00+00:00"))
    summary = asyncio.run(practice.summary())["modules"][code]
    assert summary == {"units": len(cat.modules[code].units), "mastered": 1, "practised": 1, "due": summary["due"]}


def test_course_file_names_with_a_learning_unit_number_go_to_that_unit():
    files = {"GCPP173LU02 - RR01 Fiscal deficits.pdf": SourceInfo(), "GCPP173 - Course outline.md": SourceInfo()}
    groups = module_page.group_readings(_mod("GCPP173", "GCPP173"), files, shared_kb=False)
    assert _titles(groups, "U02") == ["Fiscal deficits"]
    assert _titles(groups, "other") == ["Course outline"]
