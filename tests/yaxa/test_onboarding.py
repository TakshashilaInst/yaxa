"""Bulk onboarding: a CSV of name, email, role, track, cohort becomes logins, enrolments and faculty links."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.datastructures import UploadFile

from deeptutor.yaxa import catalog, mailer, onboarding, schedule, store
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    logins = {"old@example.org": "u-old"}
    created = []

    def create(email, password):
        assert len(password) >= 12
        uid = f"u-{len(logins)}"
        logins[email] = uid
        created.append(email)
        return uid

    monkeypatch.setattr(onboarding, "_existing_logins", lambda: dict(logins))
    monkeypatch.setattr(onboarding, "_create_login", create)
    monkeypatch.setattr(onboarding, "_me", lambda: (SimpleNamespace(id="root", is_admin=True), store.load_user("root")))
    yield created
    catalog.get_catalog(fresh=True)


def run(csv_text, email_logins=False):
    f = UploadFile(file=BytesIO(csv_text.encode()), filename="people.csv")
    return asyncio.run(onboarding.onboard(f, email_logins))


CSV = """name,email,role,track,cohort
Asha Rao,asha@example.org,student,TP,GCPP45
Old Hand,old@example.org,student,APP,GCPP45
Anupam Manur,anupam@example.org,faculty,,
"""


def test_creates_new_logins_and_enrols(_tmp_home):
    out = run(CSV)
    assert [r["ok"] for r in out["rows"]] == [True, True, True]
    assert _tmp_home == ["asha@example.org", "anupam@example.org"]  # the existing login is reused
    asha = store.load_user(out["rows"][0]["user_id"])
    assert asha.display_name == "Asha Rao" and asha.enrolments[0].cohort == "GCPP45" and asha.enrolments[0].track == "TP"
    old = store.load_user("u-old")
    assert old.enrolments[0].track == "APP"


def test_faculty_rows_become_faculty_logins(_tmp_home):
    out = run(CSV)
    u = store.load_user(out["rows"][2]["user_id"])
    assert u.role == "faculty" and u.faculty_name == "Anupam Manur"


def test_passwords_only_for_new_logins_and_only_once():
    out = run(CSV)
    lines = out["logins_csv"].strip().splitlines()
    assert lines[0] == "name,email,password"
    assert [l.split(",")[1] for l in lines[1:]] == ["asha@example.org", "anupam@example.org"]


def test_bad_rows_are_reported_and_skipped(_tmp_home):
    out = run("name,email,role,track,cohort\nX,not-an-email,student,TP,GCPP45\nY,y@example.org,student,ZZ,GCPP45\nZ,z@example.org,student,TP,NOPE\n")
    assert [r["ok"] for r in out["rows"]] == [False, False, False]
    assert _tmp_home == []


def test_wrong_header_is_422():
    with pytest.raises(HTTPException) as e:
        run("username,password\na,b\n")
    assert e.value.status_code == 422


def test_email_logins_sends_one_mail_per_new_login(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append(to))
    run(CSV, email_logins=True)
    assert sent == ["asha@example.org", "anupam@example.org"]


def test_admins_only(monkeypatch):
    monkeypatch.setattr(onboarding, "_me", lambda: (SimpleNamespace(id="x", is_admin=False), store.load_user("x")))
    with pytest.raises(HTTPException) as e:
        run(CSV)
    assert e.value.status_code == 403
