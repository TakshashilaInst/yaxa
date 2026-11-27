"""The brief: each student's private policy brief on their own problem, built one layer per session."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.yaxa import brief, catalog, community, layers, store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    yield
    catalog.get_catalog(fresh=True)


def as_user(monkeypatch, uid: str, *, track: str = "TP", staff: bool = False):
    user = store.load_user(uid, display_name=uid.title())
    user.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort="GCPP45")]
    store.save_user(user)
    monkeypatch.setattr(brief, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def words(n: int, w: str = "word") -> str:
    return " ".join([w] * n)


def approve_layer(module="GCPP-PAC", session="CP11"):
    layers.save_layer(layers.Layer(module=module, session=session, status="approved",
                                   prompt="Which institutions hold authority over your problem, and why do people accept it?",
                                   self_check=["I named the institution", "I explained legitimacy", "I named a limit"]))


class FakeModel:
    def __init__(self, reply: str):
        self.reply, self.calls, self.messages = reply, 0, None

    async def __call__(self, config, messages, max_tokens=0):
        self.calls += 1
        self.messages = messages
        return self.reply


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(brief, "resolve_for", lambda uid: object())
    fake = FakeModel(json.dumps({"critique": "You name the ministry but not why people accept it [W1].", "topic": "Drone rules for farms"}))
    monkeypatch.setattr(brief, "complete_text", fake)

    async def fake_retrieve(kb, query, top_k, corpus=""):
        return [{"title": "State", "file": "CP11.pdf", "text": "Legitimacy is accepted authority.", "kb": "GCPP"}]

    monkeypatch.setattr(brief.grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(brief, "_web_search", lambda q: [{"title": "MeitY drone rules", "url": "https://example.gov.in/drones", "snippet": "Rules of 2021."}])
    return fake


def test_empty_brief_lists_approved_layers_only(monkeypatch):
    as_user(monkeypatch, "ravi")
    approve_layer()
    layers.save_layer(layers.Layer(module="GCPP-PAC", session="CP12", prompt=words(20), self_check=["a", "b", "c"]))  # draft
    out = asyncio.run(brief.get_brief())
    assert out["problem"] == {"title": "", "text": "", "updated_at": ""}
    assert [(r["module"], r["session"]) for r in out["layers"]] == [("GCPP-PAC", "CP11")]
    assert out["layers"][0]["text"] == "" and out["layers"][0]["self_check"]


def test_problem_and_layer_saved_privately(monkeypatch):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_problem(brief.ProblemBody(title="Drone rules for farms", text="Farmers can't fly sprayers legally.")))
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="zebracrossing " * 50, ratings={"0": "yes", "2": "partly"})))
    out = asyncio.run(brief.get_brief())
    assert out["problem"]["title"] == "Drone rules for farms"
    assert out["layers"][0]["ratings"] == {"0": "yes", "2": "partly"}
    for f in community.root().rglob("*"):  # nothing outside the student's own brief file
        if f.is_file() and f.parent.name != "briefs":
            assert "zebracrossing" not in f.read_text(errors="ignore")
    as_user(monkeypatch, "asha")
    assert asyncio.run(brief.get_brief())["layers"][0]["text"] == ""  # another student sees only their own


def test_bad_ratings_rejected(monkeypatch):
    as_user(monkeypatch, "ravi")
    approve_layer()
    with pytest.raises(HTTPException) as e:
        asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="x", ratings={"0": "9/10"})))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="x", ratings={"7": "yes"})))


def test_layer_must_be_approved(monkeypatch):
    as_user(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="x")))
    assert e.value.status_code == 404


def test_critique_cites_web_and_never_rewrites(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_problem(brief.ProblemBody(title="Drone rules for farms", text="")))
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text=words(60))))
    out = asyncio.run(brief.critique("GCPP-PAC", "CP11"))
    assert "[W1]" in out["critique"] and out["sources"][0]["url"] == "https://example.gov.in/drones"
    system = model.messages[0]["content"]
    assert "never rewrite" in system.lower()
    assert "MeitY drone rules" in model.messages[1]["content"]
    saved = asyncio.run(brief.get_brief())["layers"][0]["critiques"]
    assert len(saved) == 1


def test_critique_needs_some_writing(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="too short")))
    with pytest.raises(HTTPException) as e:
        asyncio.run(brief.critique("GCPP-PAC", "CP11"))
    assert e.value.status_code == 400 and model.calls == 0


def test_critique_survives_search_failure(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text=words(60))))

    def boom(q):
        raise RuntimeError("offline")

    monkeypatch.setattr(brief, "_web_search", boom)
    out = asyncio.run(brief.critique("GCPP-PAC", "CP11"))
    assert not any(x["ref"].startswith("W") for x in out["sources"]) and out["critique"]


def test_keeps_last_three_critiques(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text=words(60))))
    for _ in range(5):
        asyncio.run(brief.critique("GCPP-PAC", "CP11"))
    assert len(asyncio.run(brief.get_brief())["layers"][0]["critiques"]) == brief.KEEP_CRITIQUES == 3


def test_export_is_markdown_of_own_work(monkeypatch):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_problem(brief.ProblemBody(title="Drone rules for farms", text="Farmers can't fly.")))
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="The DGCA holds authority.")))
    res = asyncio.run(brief.export())
    body = res.body.decode()
    assert body.startswith("# Drone rules for farms") and "The DGCA holds authority." in body
    assert "attachment" in res.headers["content-disposition"]


def test_unseen_topic_matches_track(monkeypatch, model):
    as_user(monkeypatch, "ravi", track="DFA")
    out = asyncio.run(brief.propose_unseen(brief.UnseenBody()))
    assert out["topic"] == "Drone rules for farms"
    assert "foreign policy" in model.messages[1]["content"].lower()
    asyncio.run(brief.put_unseen(brief.UnseenText(text="My take.")))
    with pytest.raises(HTTPException) as e:  # don't silently replace written work
        asyncio.run(brief.propose_unseen(brief.UnseenBody()))
    assert e.value.status_code == 409
    assert asyncio.run(brief.propose_unseen(brief.UnseenBody(replace=True)))["text"] == ""


def test_layer_status(monkeypatch):
    as_user(monkeypatch, "ravi")
    assert brief.layer_status("ravi", "GCPP-PAC", "CP11") == {"available": False, "written": False}
    approve_layer()
    assert brief.layer_status("ravi", "GCPP-PAC", "CP11") == {"available": True, "written": False}
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text="Something.")))
    assert brief.layer_status("ravi", "GCPP-PAC", "CP11") == {"available": True, "written": True}


def test_no_route_exposes_another_students_brief():
    paths = [r.path for r in brief.router.routes]
    assert paths and all(p.startswith("/brief") for p in paths)
    assert not any("{user" in p or "admin" in p or "cohort" in p for p in paths)


def test_unseen_critique_after_writing(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    asyncio.run(brief.propose_unseen(brief.UnseenBody()))
    asyncio.run(brief.put_unseen(brief.UnseenText(text=words(50))))
    out = asyncio.run(brief.critique_unseen())
    assert out["critique"] and "Drone rules for farms" in model.messages[1]["content"]
    assert len(brief.load("ravi")["unseen"]["critiques"]) == 1


def test_critique_accepts_plain_text_reply(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    approve_layer()
    asyncio.run(brief.put_layer("GCPP-PAC", "CP11", brief.LayerBody(text=words(60))))
    model.reply = "Your paragraph names one institution [W1].\n\nWho actually enforces it?"
    out = asyncio.run(brief.critique("GCPP-PAC", "CP11"))
    assert out["critique"] == "Your paragraph names one institution [W1].\n\nWho actually enforces it?"
    assert model.calls == 1
