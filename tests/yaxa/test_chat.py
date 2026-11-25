"""Cohort life, step 4: a light chat per cohort, plus one per track."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, chat, community, schedule, store
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    schedule.save_cohort(Cohort(code="GCPP46", programme="GCPP"))
    for uid, cohort, track in (("asha", "GCPP45", "DFA"), ("ravi", "GCPP45", "TP"), ("neha", "GCPP46", "DFA"),
                               ("new", "GCPP45", None)):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort=cohort)]
        store.save_user(u)
    store.save_user(store.load_user("prof", display_name="Prof"))
    store.save_user(store.load_user("loner", display_name="Loner"))
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, staff=False):
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def say(channel, text, cohort=None):
    return asyncio.run(chat.post(channel, chat.Text(text=text), cohort))


def read(channel, after="", cohort=None):
    return asyncio.run(chat.messages(channel, after, cohort))


def test_channels_by_track(monkeypatch):
    as_(monkeypatch, "asha")
    assert [c["id"] for c in asyncio.run(chat.channels(None))] == ["GCPP45", "GCPP45.DFA"]
    as_(monkeypatch, "new")
    assert [c["id"] for c in asyncio.run(chat.channels(None))] == ["GCPP45"]
    as_(monkeypatch, "loner")
    assert asyncio.run(chat.channels(None)) == []
    as_(monkeypatch, "prof", staff=True)
    assert [c["id"] for c in asyncio.run(chat.channels("GCPP45"))] == ["GCPP45", "GCPP45.APP", "GCPP45.TP", "GCPP45.DFA"]


def test_other_track_and_other_cohort_are_403(monkeypatch):
    as_(monkeypatch, "ravi")
    for ch in ("GCPP45.DFA", "GCPP46", "GCPP46.DFA"):
        with pytest.raises(HTTPException) as e:
            read(ch)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException):
            say(ch, "hi")


def test_post_read_and_after(monkeypatch):
    as_(monkeypatch, "asha")
    m1 = say("GCPP45", "Anyone doing the CS12 reading together?")
    as_(monkeypatch, "ravi")
    m2 = say("GCPP45", "Yes, Saturday 9?")
    got = read("GCPP45")
    assert [(m["author"], m["text"]) for m in got["messages"]] == [("Asha", "Anyone doing the CS12 reading together?"),
                                                                  ("Ravi", "Yes, Saturday 9?")]
    assert got["messages"][1]["mine"] and not got["messages"][0]["mine"] and got["me"] == "ravi"
    assert [m["id"] for m in read("GCPP45", after=m1["id"])["messages"]] == [m2["id"]]
    as_(monkeypatch, "neha")
    assert read("GCPP46")["messages"] == []


def test_edit_window_and_staff_hide(monkeypatch):
    as_(monkeypatch, "asha")
    m = say("GCPP45", "typo hre")
    asyncio.run(chat.edit("GCPP45", m["id"], chat.Text(text="typo here")))
    assert read("GCPP45")["messages"][0]["text"] == "typo here" and read("GCPP45")["messages"][0]["edited"]
    as_(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat.edit("GCPP45", m["id"], chat.Text(text="hacked")))
    assert e.value.status_code == 403
    as_(monkeypatch, "asha")
    monkeypatch.setattr(community, "EDIT_WINDOW", -1)
    with pytest.raises(HTTPException):
        asyncio.run(chat.remove("GCPP45", m["id"]))
    as_(monkeypatch, "prof", staff=True)
    asyncio.run(chat.remove("GCPP45", m["id"], "GCPP45"))
    as_(monkeypatch, "asha")
    assert read("GCPP45")["messages"] == []


def test_closed_rate_limit_and_length(monkeypatch):
    as_(monkeypatch, "asha")
    monkeypatch.setattr(chat, "PER_HOUR", 2)
    say("GCPP45", "one")
    say("GCPP45", "two")
    with pytest.raises(HTTPException) as e:
        say("GCPP45", "three")
    assert e.value.status_code == 429
    with pytest.raises(HTTPException) as e:
        say("GCPP45.DFA", "x" * 2001)
    assert e.value.status_code == 400
    c = schedule.load_cohort("GCPP45")
    c.closed = True
    schedule.save_cohort(c)
    assert read("GCPP45")["closed"] is True
    with pytest.raises(HTTPException) as e:
        say("GCPP45.DFA", "hello")
    assert e.value.status_code == 403
