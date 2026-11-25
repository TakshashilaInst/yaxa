"""Cohort life, step 3: per-session discussion. Yaxa drafts an answer from the
readings; faculty confirm or correct it; confirmed threads help later cohorts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, community, discussion, schedule, store
from deeptutor.yaxa.llm import ModelUnavailable
from deeptutor.yaxa.schedule import Cohort

MOD, SES = "DFA-SSIR", "CS12"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    schedule.save_cohort(Cohort(code="GCPP46", programme="GCPP"))
    for uid, cohort in (("asha", "GCPP45"), ("ravi", "GCPP45"), ("neha", "GCPP46")):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track="DFA", cohort=cohort)]
        store.save_user(u)
    store.save_user(store.load_user("prof", display_name="Prof Menon"))
    store.save_user(store.load_user("loner", display_name="Loner"))

    async def fake_retrieve(kb, query, top_k, corpus=""):
        return [{"kb": kb, "file": "deterrence.pdf", "title": "Deterrence basics", "text": "Deterrence is ..."}]

    calls = []

    async def fake_complete(config, messages, max_tokens=1500):
        calls.append(messages)
        return "Deterrence works by threat of cost [1]."

    monkeypatch.setattr(discussion.grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(discussion, "complete_text", fake_complete)
    monkeypatch.setattr(discussion, "resolve_for", lambda uid: object())
    monkeypatch.setattr(discussion, "_calls", calls, raising=False)
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, staff=False):
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def ask(text="Why does nuclear deterrence work?"):
    return asyncio.run(discussion.ask(MOD, SES, discussion.Text(text=text)))


def view(cohort=None):
    return asyncio.run(discussion.thread_list(MOD, SES, cohort))


def test_ask_drafts_yaxa_answer_with_sources(monkeypatch):
    as_(monkeypatch, "asha")
    t = ask()
    assert t["author"] == "Asha" and t["mine"]
    assert t["yaxa"]["status"] == "ok" and "[1]" in t["yaxa"]["answer"]
    assert [(x["n"], x["title"]) for x in t["yaxa"]["sources"]] == [(1, "Deterrence basics")]
    assert "text" not in t["yaxa"]["sources"][0]  # passage text is not copied into the thread
    assert store.load_user("asha").turns_today == 1  # counts as the asker's turn
    as_(monkeypatch, "ravi")
    got = view()
    assert got["cohort"] == "GCPP45" and [x["text"] for x in got["threads"]] == ["Why does nuclear deterrence work?"]
    assert not got["threads"][0]["mine"]


def test_model_unavailable_still_saves(monkeypatch):
    def nope(uid):
        raise ModelUnavailable("off")

    monkeypatch.setattr(discussion, "resolve_for", nope)
    as_(monkeypatch, "asha")
    t = ask()
    assert t["yaxa"]["status"] == "unavailable" and t["yaxa"]["answer"] == ""
    assert len(view()["threads"]) == 1


def test_model_error_still_saves(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(discussion, "complete_text", boom)
    as_(monkeypatch, "asha")
    assert ask()["yaxa"]["status"] == "unavailable"


def test_also_reply_and_review(monkeypatch):
    as_(monkeypatch, "asha")
    t = ask()
    as_(monkeypatch, "ravi")
    assert asyncio.run(discussion.also(MOD, SES, t["id"]))["also"] == 1
    assert asyncio.run(discussion.also(MOD, SES, t["id"]))["also"] == 0  # toggles
    asyncio.run(discussion.also(MOD, SES, t["id"]))
    asyncio.run(discussion.reply(MOD, SES, t["id"], discussion.Text(text="I think it's about credibility.")))
    with pytest.raises(HTTPException) as e:
        asyncio.run(discussion.review(MOD, SES, t["id"], discussion.Review(status="confirmed")))
    assert e.value.status_code == 403
    as_(monkeypatch, "prof", staff=True)
    asyncio.run(discussion.review(MOD, SES, t["id"], discussion.Review(status="corrected", note="Also second-strike capability."),
                                  cohort="GCPP45"))
    asyncio.run(discussion.reply(MOD, SES, t["id"], discussion.Text(text="Good question."), cohort="GCPP45"))
    got = view("GCPP45")["threads"][0]
    assert got["also"] == 1 and got["review"]["status"] == "corrected" and got["review"]["by"] == "Prof Menon"
    assert [(r["author"], r["staff"]) for r in got["replies"]] == [("Ravi", False), ("Prof Menon", True)]


def test_corrected_needs_note(monkeypatch):
    as_(monkeypatch, "asha")
    t = ask()
    as_(monkeypatch, "prof", staff=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(discussion.review(MOD, SES, t["id"], discussion.Review(status="corrected"), cohort="GCPP45"))
    assert e.value.status_code == 400


def test_past_cohort_threads_anonymised_and_only_reviewed(monkeypatch):
    as_(monkeypatch, "asha")
    reviewed = ask("Reviewed question")
    ask("Unreviewed question")
    as_(monkeypatch, "ravi")
    asyncio.run(discussion.reply(MOD, SES, reviewed["id"], discussion.Text(text="Learner reply")))
    as_(monkeypatch, "prof", staff=True)
    asyncio.run(discussion.review(MOD, SES, reviewed["id"], discussion.Review(status="confirmed"), cohort="GCPP45"))
    asyncio.run(discussion.reply(MOD, SES, reviewed["id"], discussion.Text(text="Faculty note"), cohort="GCPP45"))
    as_(monkeypatch, "neha")
    got = view()
    assert got["cohort"] == "GCPP46" and got["threads"] == []
    assert [p["text"] for p in got["past"]] == ["Reviewed question"]
    past = got["past"][0]
    blob = repr(past)
    assert "Asha" not in blob and "asha" not in blob and "Ravi" not in blob and "Learner reply" not in blob
    assert past["cohort"] == "GCPP45" and [r["text"] for r in past["replies"]] == ["Faculty note"]
    assert past["replies"][0]["author"] == "Faculty" and past["review"]["by"] == "Faculty"


def test_closed_cohort_is_read_only(monkeypatch):
    as_(monkeypatch, "asha")
    ask()
    c = schedule.load_cohort("GCPP45")
    c.closed = True
    schedule.save_cohort(c)
    assert view()["closed"] is True
    with pytest.raises(HTTPException) as e:
        ask()
    assert e.value.status_code == 403


def test_delete_window(monkeypatch):
    as_(monkeypatch, "asha")
    t = ask()
    as_(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(discussion.remove(MOD, SES, t["id"]))
    assert e.value.status_code == 403
    as_(monkeypatch, "asha")
    monkeypatch.setattr(community, "EDIT_WINDOW", -1)
    with pytest.raises(HTTPException):
        asyncio.run(discussion.remove(MOD, SES, t["id"]))
    monkeypatch.setattr(community, "EDIT_WINDOW", 900)
    asyncio.run(discussion.remove(MOD, SES, t["id"]))
    assert view()["threads"] == []


def test_queue_puts_unanswered_first(monkeypatch):
    as_(monkeypatch, "asha")
    a = ask("First")
    ask("Second")
    as_(monkeypatch, "prof", staff=True)
    asyncio.run(discussion.review(MOD, SES, a["id"], discussion.Review(status="confirmed"), cohort="GCPP45"))
    q = asyncio.run(discussion.queue("GCPP45"))
    assert [x["text"] for x in q] == ["Second", "First"] and q[0]["session"] == SES and q[0]["module"] == MOD


def test_rate_limit_and_no_cohort_and_bad_session(monkeypatch):
    as_(monkeypatch, "asha")
    monkeypatch.setattr(discussion, "QUESTIONS_PER_HOUR", 1)
    ask()
    with pytest.raises(HTTPException) as e:
        ask()
    assert e.value.status_code == 429
    with pytest.raises(HTTPException) as e:
        asyncio.run(discussion.thread_list(MOD, "CT31", None))
    assert e.value.status_code == 404
    as_(monkeypatch, "loner")
    store_u = store.load_user("loner")
    store_u.enrolments = [store.Enrolment(programme="GCPP", track="DFA")]
    store.save_user(store_u)
    got = view()
    assert got["cohort"] is None and got["threads"] == []
    with pytest.raises(HTTPException) as e:
        ask()
    assert e.value.status_code == 404
