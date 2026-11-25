"""Cohort life, step 2: announcements in Yaxa, emailed to the cohort's group."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import announcements as ann
from deeptutor.yaxa import catalog, community, schedule, store
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP", email_group="gcpp45@example.org",
                                track_email_groups={"DFA": "gcpp45-dfa@example.org"}))
    schedule.save_cohort(Cohort(code="GCPP46", programme="GCPP"))
    for uid, track in (("asha", "DFA"), ("ravi", "TP")):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort="GCPP45")]
        store.save_user(u)
    store.save_user(store.load_user("boss", display_name="Programme Office"))
    store.save_user(store.load_user("loner", display_name="Loner"))
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, staff=False):
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def post(**kw):
    body = dict(cohort="GCPP45", title="CS12 moves to 2 pm", body="Same link.")
    body.update(kw)
    return asyncio.run(ann.create(ann.NewAnnouncement(**body)))


def test_learner_cannot_post(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        post()
    assert e.value.status_code == 403


def test_not_configured_gives_mailto_and_shows_in_yaxa(monkeypatch):
    as_(monkeypatch, "boss", staff=True)
    r = post(session="CS12")
    assert r["email"] == "not_configured"
    assert r["mailto"].startswith("mailto:gcpp45@example.org?subject=%5BGCPP45%5D%20CS12%20moves")
    assert r["item"]["session"] == "CS12" and r["item"]["module"] == "DFA-SSIR"
    as_(monkeypatch, "asha")
    got = asyncio.run(ann.listing(None))
    assert [i["title"] for i in got["items"]] == ["CS12 moves to 2 pm"] and got["unread"] == 1


def test_track_only_items_and_track_group(monkeypatch):
    sent = []
    monkeypatch.setattr(ann.mailer, "configured", lambda: True)
    monkeypatch.setattr(ann.mailer, "send", lambda to, subject, text: sent.append((to, subject)))
    as_(monkeypatch, "boss", staff=True)
    r = post(title="DFA only", track="DFA")
    assert r["email"] == "sent" and sent == [("gcpp45-dfa@example.org", "[GCPP45] DFA only")]
    as_(monkeypatch, "ravi")
    assert asyncio.run(ann.listing(None))["items"] == []
    as_(monkeypatch, "asha")
    assert len(asyncio.run(ann.listing(None))["items"]) == 1


def test_email_never_sent_twice(monkeypatch):
    sent = []
    monkeypatch.setattr(ann.mailer, "configured", lambda: True)
    monkeypatch.setattr(ann.mailer, "send", lambda *a: sent.append(a))
    as_(monkeypatch, "boss", staff=True)
    r = post()
    with pytest.raises(HTTPException) as e:
        asyncio.run(ann.email_again("GCPP45", r["item"]["id"]))
    assert e.value.status_code == 409 and len(sent) == 1


def test_failed_email_can_be_retried(monkeypatch):
    monkeypatch.setattr(ann.mailer, "configured", lambda: True)

    def boom(*a):
        raise OSError("smtp down")

    monkeypatch.setattr(ann.mailer, "send", boom)
    as_(monkeypatch, "boss", staff=True)
    r = post()
    assert r["email"] == "failed" and r["item"]["emailed_at"] == ""
    monkeypatch.setattr(ann.mailer, "send", lambda *a: None)
    assert asyncio.run(ann.email_again("GCPP45", r["item"]["id"]))["email"] == "sent"


def test_seen_clears_unread_and_hidden_disappears(monkeypatch):
    as_(monkeypatch, "boss", staff=True)
    a = post(title="One")["item"]
    post(title="Two")
    as_(monkeypatch, "asha")
    assert asyncio.run(ann.listing(None))["unread"] == 2
    asyncio.run(ann.mark_seen())
    assert asyncio.run(ann.listing(None))["unread"] == 0
    as_(monkeypatch, "boss", staff=True)
    asyncio.run(ann.hide("GCPP45", a["id"]))
    as_(monkeypatch, "asha")
    assert [i["title"] for i in asyncio.run(ann.listing(None))["items"]] == ["Two"]


def test_no_cohort_is_empty_and_other_cohort_unseen(monkeypatch):
    as_(monkeypatch, "boss", staff=True)
    post(cohort="GCPP46", title="For 46")
    as_(monkeypatch, "loner")
    assert asyncio.run(ann.listing(None)) == {"cohort": None, "items": [], "unread": 0}
    asyncio.run(ann.mark_seen())  # no crash
    as_(monkeypatch, "asha")
    assert asyncio.run(ann.listing("GCPP46"))["items"] == []


def test_too_long_is_400(monkeypatch):
    as_(monkeypatch, "boss", staff=True)
    with pytest.raises(HTTPException) as e:
        post(body="x" * 4001)
    assert e.value.status_code == 400
