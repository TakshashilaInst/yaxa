"""What's new since a learner's last visit: cohort chat, their discussion questions, announcements."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.yaxa import catalog, chat, community, schedule, store, whats_new
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    for uid, track in (("asha", "DFA"), ("ravi", "TP")):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort="GCPP45")]
        store.save_user(u)
    store.save_user(store.load_user("loner", display_name="Loner"))
    tick = iter(range(10_000))  # a clock that moves on every call: real timestamps are to the second
    monkeypatch.setattr(community, "now_iso", lambda: f"2027-01-01T00:{next(tick):05d}")
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, staff=False):
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def say(channel, text):
    return asyncio.run(chat.post(channel, chat.Text(text=text), None))


def news():
    return asyncio.run(whats_new.whats_new())


def seen(area):
    return asyncio.run(whats_new.mark_seen(whats_new.Seen(area=area)))


def test_counts_others_messages_in_my_channels_only(monkeypatch):
    as_(monkeypatch, "ravi")
    say("GCPP45", "hello all")
    say("GCPP45.TP", "tp only")
    as_(monkeypatch, "asha")
    say("GCPP45", "my own message")
    n = news()
    assert n["chat"] == 1  # ravi's cohort message; not TP's channel, not her own
    assert n["cohort"] == "GCPP45"


def test_seen_resets_chat_count(monkeypatch):
    as_(monkeypatch, "ravi")
    say("GCPP45", "hello")
    as_(monkeypatch, "asha")
    assert news()["chat"] == 1
    seen("chat")
    assert news()["chat"] == 0
    as_(monkeypatch, "ravi")
    say("GCPP45", "again")
    as_(monkeypatch, "asha")
    assert news()["chat"] == 1


def test_replies_and_reviews_on_my_questions(monkeypatch):
    path = community.root("discussion", "GCPP45") / "CP11.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    later = "2026-06-01T00:00:00+00:00"
    store._write_json(path, [
        {"id": "q1", "author_id": "asha", "author": "Asha", "text": "Why?", "created_at": "2026-01-01T00:00:00+00:00",
         "yaxa": {}, "replies": [
             {"id": "r1", "author_id": "ravi", "author": "Ravi", "staff": False, "text": "Because", "created_at": later},
             {"id": "r2", "author_id": "asha", "author": "Asha", "staff": False, "text": "Thanks", "created_at": later}],
         "review": {"status": "confirmed", "at": later}},
        {"id": "q2", "author_id": "ravi", "author": "Ravi", "text": "Not mine", "created_at": later, "yaxa": {},
         "replies": [{"id": "r3", "author_id": "x", "author": "X", "staff": False, "text": "hi", "created_at": later}]},
    ])
    as_(monkeypatch, "asha")
    n = news()
    assert n["discussion"] == 2  # ravi's reply + the faculty review; not her own reply, not ravi's thread
    assert n["discussion_where"] == [{"module": "GCPP-Fundamentals", "session": "CP11"}]
    seen("discussion")
    assert news()["discussion"] == 0


def test_no_cohort_is_all_zero(monkeypatch):
    as_(monkeypatch, "loner")
    assert news() == {"cohort": None, "chat": 0, "discussion": 0, "discussion_where": [], "announcements": 0}


def test_unknown_area_is_400(monkeypatch):
    from fastapi import HTTPException
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        seen("everything")
    assert e.value.status_code == 400
