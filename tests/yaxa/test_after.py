"""After the session: a faculty-approved note per cohort and session (what we discussed, what's still open)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import after, catalog, schedule, store
from deeptutor.yaxa.schedule import Cohort

MOD, SES = "GCPP-Fundamentals", "CP11"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    schedule.save_cohort(Cohort(code="GCPP46", programme="GCPP"))
    for uid, c in (("asha", "GCPP45"), ("neha", "GCPP46")):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track="TP", cohort=c)]
        store.save_user(u)
    tr = tmp_path / "t.txt"
    tr.write_text("Lecturer: today we argued whether the State is the nation...")
    monkeypatch.setattr(after, "transcripts", lambda m, s: [{"file": "t.txt", "title": "Webinar CP11", "path": tr}])
    prompts = []

    async def fake_complete(config, messages, max_tokens=1500):
        prompts.append(messages[-1]["content"])
        return '{"discussed": ["Nation and State are different things"], "open": ["Is India a State-nation?"]}'

    monkeypatch.setattr(after, "complete_text", fake_complete)
    monkeypatch.setattr(after, "resolve_for", lambda uid: object())
    monkeypatch.setattr(after, "_prompts", prompts, raising=False)
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, admin=False):
    monkeypatch.setattr(after, "_me", lambda: (SimpleNamespace(id=uid, is_admin=admin), store.load_user(uid)))


def test_draft_from_a_transcript_is_not_live(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    n = asyncio.run(after.draft("GCPP45", MOD, SES, after.DraftBody(file="t.txt")))
    assert n["status"] == "draft" and n["discussed"] == ["Nation and State are different things"]
    assert "State is the nation" in after._prompts[0]
    assert after.approved_note("GCPP45", MOD, SES) is None


def test_approved_note_reaches_only_that_cohort(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    asyncio.run(after.save("GCPP45", MOD, SES, after.EditBody(discussed=["We discussed X"], open=["Y?"], recording_url="https://drive.google.com/x")))
    asyncio.run(after.approve("GCPP45", MOD, SES))
    assert after.approved_note("GCPP45", MOD, SES)["discussed"] == ["We discussed X"]
    assert after.approved_note("GCPP46", MOD, SES) is None


def test_save_needs_something_discussed(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(after.save("GCPP45", MOD, SES, after.EditBody(discussed=[" "], open=[])))
    assert e.value.status_code == 400


def test_recording_link_must_be_https(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    with pytest.raises(HTTPException):
        asyncio.run(after.save("GCPP45", MOD, SES, after.EditBody(discussed=["a"], recording_url="javascript:alert(1)")))


def test_unknown_transcript_is_404(monkeypatch):
    as_(monkeypatch, "root", admin=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(after.draft("GCPP45", MOD, SES, after.DraftBody(file="../../secrets.txt")))
    assert e.value.status_code == 404


def test_students_cannot_edit(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(after.get_note("GCPP45", MOD, SES))
    assert e.value.status_code == 403
