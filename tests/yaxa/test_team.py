"""Faculty team: who teaches which module, and which login belongs to which faculty member."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import access, catalog, store, team


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    for uid in ("anupam", "asha"):
        store.save_user(store.load_user(uid, display_name=uid.title()))
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, admin=False):
    monkeypatch.setattr(team, "_me", lambda: (SimpleNamespace(id=uid, is_admin=admin), store.load_user(uid)))


def test_roster_starts_from_the_content_file(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    rows = {m["code"]: m["faculty"] for m in asyncio.run(team.get_team())["modules"]}
    assert rows["APP-ER2"] == ["Anupam Manur", "Sarthak Pradhan"]
    assert rows["GCPP-COMM"] == ["Ganesh"]


def test_admin_edits_a_module_roster(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    asyncio.run(team.set_module("GCPP-COMM", team.Names(faculty=["Ganesh", " ", "Ganesh", "Nitin Pai"])))
    assert team.faculty_for("GCPP-COMM") == ["Ganesh", "Nitin Pai"]


def test_unknown_module_is_404(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(team.set_module("NOPE", team.Names(faculty=["X"])))
    assert e.value.status_code == 404


def test_linking_a_login_makes_it_faculty_and_gives_its_modules(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    asyncio.run(team.set_account("anupam", team.Link(name="Anupam Manur")))
    u = store.load_user("anupam")
    assert u.role == "faculty" and u.faculty_name == "Anupam Manur"
    assert access._privileged(SimpleNamespace(is_admin=False), u)
    assert set(team.teaches(u)) == {"GCPP-ER1", "APP-ER2"}


def test_unlinking_returns_the_login_to_student(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    asyncio.run(team.set_account("anupam", team.Link(name="Anupam Manur")))
    asyncio.run(team.set_account("anupam", team.Link(name="")))
    u = store.load_user("anupam")
    assert u.role == "student" and u.faculty_name == "" and team.teaches(u) == []


def test_only_admins_change_the_team(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    asyncio.run(team.set_account("anupam", team.Link(name="Anupam Manur")))
    as_(monkeypatch, "anupam")  # faculty can read the team, not change it
    assert asyncio.run(team.get_team())["modules"]
    with pytest.raises(HTTPException) as e:
        asyncio.run(team.set_account("asha", team.Link(name="Anupam Manur")))
    assert e.value.status_code == 403


def test_students_cannot_read_the_team(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(team.get_team())
    assert e.value.status_code == 403
