"""Brief layer prompts: per session, Yaxa drafts the layer task and self-check; faculty approve."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.yaxa import catalog, community, layers, store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    yield
    catalog.get_catalog(fresh=True)


def as_user(monkeypatch, uid: str, *, staff: bool = False):
    user = store.load_user(uid, display_name=uid.title())
    user.enrolments = [store.Enrolment(programme="GCPP", track="TP")]
    store.save_user(user)
    monkeypatch.setattr(layers, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def _layer(**kw) -> layers.Layer:
    base = dict(module="GCPP-PAC", session="CP11", prompt="Which institutions hold authority over your problem, and why do people accept it?",
                self_check=["I named the institution", "I said where its legitimacy comes from", "I named a constitutional limit"])
    base.update(kw)
    return layers.Layer(**base)


class FakeModel:
    def __init__(self, reply: str):
        self.reply, self.calls, self.messages = reply, 0, None

    async def __call__(self, config, messages, max_tokens=0):
        self.calls += 1
        self.messages = messages
        return self.reply


DRAFT = json.dumps({"prompt": "Which institutions hold authority over your problem, and why do people accept it?",
                    "self_check": ["I named the institution", "I explained legitimacy", "I named a limit"]})


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(layers, "resolve_for", lambda uid: object())
    fake = FakeModel(DRAFT)
    monkeypatch.setattr(layers, "complete_text", fake)
    return fake


def test_validate():
    assert layers.validate(_layer()) == []
    assert layers.validate(_layer(prompt="short"))
    assert layers.validate(_layer(self_check=["one", "two"]))
    assert layers.validate(_layer(self_check=[f"q{i}" for i in range(6)]))


def test_hint_from_mapping_table():
    assert "authority" in layers.hint_for("GCPP-PAC", "CP11").lower()
    assert "bardach" in layers.hint_for("TP-RS", "CT23").lower()
    assert "market failure" in layers.hint_for("TP-IE", "CT3x").lower()
    assert "second-order" in layers.hint_for("TP-IE", "CP44").lower()
    assert "technology" in layers.hint_for("TP-AI", "CT41").lower()
    assert layers.hint_for("GCPP173", "U01") == ""


def test_draft_uses_hint_and_saves_draft(monkeypatch, model):
    as_user(monkeypatch, "boss", staff=True)
    out = asyncio.run(layers.admin_draft("GCPP-PAC", "CP11"))
    assert out["status"] == "draft" and len(out["self_check"]) == 3
    assert "authority" in model.messages[1]["content"].lower()
    assert layers.approved_layer("GCPP-PAC", "CP11") is None


def test_approve_then_visible(monkeypatch):
    as_user(monkeypatch, "boss", staff=True)
    layers.save_layer(_layer())
    out = asyncio.run(layers.admin_approve("GCPP-PAC", "CP11"))
    assert out["status"] == "approved" and out["approved_by"] == "Boss"
    assert layers.approved_layer("GCPP-PAC", "CP11").prompt.startswith("Which")
    asyncio.run(layers.admin_unpublish("GCPP-PAC", "CP11"))
    assert layers.approved_layer("GCPP-PAC", "CP11") is None


def test_edit_invalid_is_400(monkeypatch):
    as_user(monkeypatch, "boss", staff=True)
    layers.save_layer(_layer())
    with pytest.raises(HTTPException) as e:
        asyncio.run(layers.admin_save("GCPP-PAC", "CP11", layers.EditBody(prompt="x", self_check=["a", "b", "c"])))
    assert e.value.status_code == 400


def test_student_cannot_draft(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(layers.admin_draft("GCPP-PAC", "CP11"))
    assert e.value.status_code == 403 and e.value.detail == "Layer prompts are edited by faculty" and model.calls == 0


def test_admin_list(monkeypatch):
    as_user(monkeypatch, "boss", staff=True)
    layers.save_layer(_layer(status="approved"))
    rows = asyncio.run(layers.admin_list("GCPP-PAC"))
    assert next(r for r in rows if r["session"] == "CP11")["status"] == "approved"
    assert next(r for r in rows if r["session"] == "CP10")["status"] == "none"
    assert next(r for r in rows if r["session"] == "CP10")["hint"]
