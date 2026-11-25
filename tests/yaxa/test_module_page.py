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
            Unit(id="CT31", title="Nature and Pricing of Information Goods", lms_url="https://lms/ct31"),
            Unit(id="CT33", title="Switching Costs and Lock-In"),
            Unit(id="CT3x", title="Market Failures", aliases=["CT37"]),
            Unit(id="CP44", title="Complexity"),
        ],
    )


def _titles(groups: dict, key: str) -> list[str]:
    return [r["title"] for r in groups[key]]


def test_files_go_to_the_unit_with_their_session_code():
    files = {
        "CT31 - a.pdf": SourceInfo(title="CT31 Nature and Pricing of Information Goods: Capitalism Without Capital", unit="CT31", module="TP-IE"),
        "CT33 - b.pdf": SourceInfo(title="CT33 Switching Costs and Lock-In: Farrell", unit="CT33", module="TP-IE"),
        "Webinar - x.md": SourceInfo(title="Webinar: CT33 Switching costs, Nitin Pai", kind="video", unit="U02", module="TP-IE"),
    }
    groups = module_page.group_readings(_mod(), files, shared_kb=True)
    assert _titles(groups, "CT31") == ["CT31 Nature and Pricing of Information Goods: Capitalism Without Capital"]
    assert _titles(groups, "CT33") == ["CT33 Switching Costs and Lock-In: Farrell", "Webinar: CT33 Switching costs, Nitin Pai"]
    assert groups["other"] == []


def test_older_codes_reach_the_session_that_replaced_them():
    files = {"CT37 - m.pdf": SourceInfo(title="CT37 Market failures reading", unit="CT37", module="TP-IE")}
    assert _titles(module_page.group_readings(_mod(), files, shared_kb=True), "CT3x") == ["CT37 Market failures reading"]


def test_a_file_tagged_to_another_module_comes_here_only_if_that_module_lacks_the_session():
    files = {
        "CP44 - c.pdf": SourceInfo(title="CP44 Complexity reading", unit="CP44", module="TP-RS"),  # TP-RS has no CP44
        "CT31 - d.pdf": SourceInfo(title="CT31 reading kept by APP", unit="CT31", module="APP-ER2"),  # APP-ER2 has CT31
    }
    owners = {"TP-RS": {"CT21", "CT24"}, "APP-ER2": {"CT31"}}
    groups = module_page.group_readings(_mod(), files, shared_kb=True, owners=owners)
    assert _titles(groups, "CP44") == ["CP44 Complexity reading"]
    assert groups["CT31"] == []


def test_untagged_or_unknown_code_files_of_this_module_are_whole_module_readings():
    files = {
        "guide.md": SourceInfo(title="Module guide", kind="note", module="TP-IE"),
        "CT3 - z.pdf": SourceInfo(title="CT3 overview", unit="CT3", module="TP-IE"),
        "elsewhere.pdf": SourceInfo(title="Untagged in a shared library"),
        "old.pdf": SourceInfo(title="CT31 old", unit="CT31", module="TP-IE", retired=True),
    }
    groups = module_page.group_readings(_mod(), files, shared_kb=True)
    assert _titles(groups, "other") == ["CT3 overview", "Module guide"]
    assert all(not groups[u] for u in ("CT31", "CT33", "CT3x", "CP44"))


def test_webinars_without_a_code_match_by_unit_title():
    mod = Module(code="APP-ER2", title="ER2", kb="APP", units=[Unit(id="CP52", title="Externalities"), Unit(id="CP54", title="Information Asymmetry")])
    files = {"w.md": SourceInfo(title="Webinar: Market Failures - Externalities", kind="video", unit="U02", module="APP-ER2")}
    assert _titles(module_page.group_readings(mod, files, shared_kb=True), "CP52") == ["Webinar: Market Failures - Externalities"]


def test_modules_without_codes_still_use_unit_numbers_in_file_names():
    mod = Module(code="GCPP173", title="PF", kb="GCPP173", units=[Unit(id="U01", title="Introduction"), Unit(id="U02", title="Macro")])
    files = {"GCPP173LU02 - RR01 Fiscal deficits.pdf": SourceInfo(), "GCPP173 - Course outline.md": SourceInfo()}
    groups = module_page.group_readings(mod, files, shared_kb=False)
    assert _titles(groups, "U02") == ["Fiscal deficits"]
    assert _titles(groups, "other") == ["Course outline"]


def test_links_open_readings_in_yaxa_and_recordings_on_drive():
    mod = Module(code="GCPP-ER1", title="ER1", kb="GCPP-ER1", units=[Unit(id="CP21", title="Introduction to Economic Reasoning")])
    files = {
        "CP21.pdf": SourceInfo(title="CP21 reading: Paper", kind="pdf", unit="CP21"),
        "Webinar - CP21.md": SourceInfo(title="Webinar: CP21 Introduction to Economic Reasoning", kind="video",
                                        url="https://drive.google.com/file/d/abc/view", corpus="Webinar recording, GCPP44 (May 2026)"),
        "op-ed.md": SourceInfo(title="CP21 An op-ed", kind="note", unit="CP21", url="https://theprint.in/x"),
    }
    rows = {r["title"]: r for r in module_page.group_readings(mod, files, shared_kb=False)["CP21"]}
    assert rows["CP21 reading: Paper"]["open"] == "/api/yaxa/files/GCPP-ER1/CP21.pdf"
    webinar = rows["Webinar: CP21 Introduction to Economic Reasoning"]
    assert webinar["open"] == "/api/yaxa/files/GCPP-ER1/Webinar - CP21.md"  # transcript
    assert webinar["watch"] == "https://drive.google.com/file/d/abc/view"  # the recording
    assert rows["CP21 An op-ed"]["open"] == "https://theprint.in/x"


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


def test_a_file_whose_session_lives_in_a_sibling_module_is_not_repeated_here():
    rs = Module(code="TP-RS", title="RS", kb="TP", units=[Unit(id="CT21", title="Social Impact Analysis and Responsible Strategy")])
    files = {"CP44 - c.pdf": SourceInfo(title="CP44 Complexity: Stocks and Flows", unit="CP44", module="TP-RS")}
    groups = module_page.group_readings(rs, files, shared_kb=True, owners={"TP-IE": {"CP44"}})
    assert groups["other"] == [] and groups["CT21"] == []


def test_short_webinar_titles_match_the_longer_session_title():
    mod = Module(code="APP-PAF", title="PAF", kb="APP", units=[
        Unit(id="CP43", title="Effecting Change"),
        Unit(id="CP45", title="Implementation Frameworks and Banishing Bureaucracy")])
    files = {
        "w.md": SourceInfo(title="Webinar: Implementation Frameworks", kind="video", module="APP-PAF"),
        "x.md": SourceInfo(title="Webinar: Change, Someone", kind="video", module="APP-PAF"),  # too short to trust
    }
    groups = module_page.group_readings(mod, files, shared_kb=True)
    assert _titles(groups, "CP45") == ["Webinar: Implementation Frameworks"]
    assert _titles(groups, "other") == ["Webinar: Change, Someone"]


def test_students_get_no_drive_links_until_recordings_are_shared_with_them(monkeypatch):
    cu, user = _student()
    cat = catalog.get_catalog()
    code = next(c for c in access._allowed_modules(cat, cu, user) if cat.modules[c].units)
    unit = cat.modules[code].units[0]
    webinar = {"Webinar - x.md": SourceInfo(title=f"Webinar: {unit.id} {unit.title}", kind="video", module=code,
                                            url="https://drive.google.com/file/d/abc/view")}
    monkeypatch.setattr(module_page, "_files", lambda kb: webinar)
    monkeypatch.setattr(module_page, "_me", lambda: (cu, user))
    row = asyncio.run(module_page.module_view(code))["units"][0]["readings"][0]
    assert "watch" not in row and row["open"].endswith("Webinar - x.md")
    staff = SimpleNamespace(id="a1", is_admin=True)
    monkeypatch.setattr(module_page, "_me", lambda: (staff, store.load_user("a1", display_name="Admin")))
    assert asyncio.run(module_page.module_view(code))["units"][0]["readings"][0]["watch"].startswith("https://drive")
