"""Students' own AI keys: stored encrypted, never returned, used for that student's model calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.yaxa import catalog, community, keys, llm, store

SECRET_KEY = "sk-ant-test-0000000000000000000000000000wxyz"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    monkeypatch.delenv("YAXA_KEY_SECRET", raising=False)
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    monkeypatch.setattr(llm, "_staff_ids", lambda: {"boss"})
    yield
    catalog.get_catalog(fresh=True)


def as_user(monkeypatch, uid: str):
    store.save_user(store.load_user(uid, display_name=uid.title()))
    monkeypatch.setattr(keys, "_me", lambda: (SimpleNamespace(id=uid, is_admin=False), store.load_user(uid)))


@pytest.fixture
def key_ok(monkeypatch):
    calls = []

    async def fake(config, messages, max_tokens=0):
        calls.append(config)
        return "OK"

    monkeypatch.setattr(keys, "complete_text", fake)
    return calls


def test_saved_key_is_encrypted_and_never_returned(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    out = asyncio.run(keys.put_key(keys.KeyBody(provider="anthropic", key=SECRET_KEY)))
    assert out == {"provider": "anthropic", "model": keys.DEFAULT_MODELS["anthropic"], "hint": "…wxyz", "set_at": out["set_at"]}
    assert SECRET_KEY not in json.dumps(asyncio.run(keys.get_key()))
    for f in store.yaxa_root().rglob("*"):
        if f.is_file():
            assert SECRET_KEY not in f.read_text(errors="ignore")
    assert key_ok[0].api_key == SECRET_KEY and key_ok[0].provider_name == "anthropic"


def test_bad_key_is_not_saved(monkeypatch):
    as_user(monkeypatch, "ravi")

    async def fail(config, messages, max_tokens=0):
        raise RuntimeError(f"401 invalid x-api-key {config.api_key}")

    monkeypatch.setattr(keys, "complete_text", fail)
    with pytest.raises(HTTPException) as e:
        asyncio.run(keys.put_key(keys.KeyBody(provider="anthropic", key=SECRET_KEY)))
    assert e.value.status_code == 400 and SECRET_KEY not in str(e.value.detail)
    assert asyncio.run(keys.get_key()) == {"provider": None}


def test_unknown_provider_rejected(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(keys.put_key(keys.KeyBody(provider="acme", key=SECRET_KEY)))
    assert e.value.status_code == 400 and not key_ok


def test_delete(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    asyncio.run(keys.put_key(keys.KeyBody(provider="openai", key="sk-proj-abcdefghijklmnop1234", model="gpt-5")))
    asyncio.run(keys.delete_key())
    assert keys.config_for("ravi") is None


def test_openai_config(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    asyncio.run(keys.put_key(keys.KeyBody(provider="openai", key="sk-proj-abcdefghijklmnop1234", model="gpt-5")))
    c = keys.config_for("ravi")
    assert c.provider_name == "openai" and c.model == "gpt-5" and c.base_url == "https://api.openai.com/v1"


def _mode(monkeypatch, mode: str):
    monkeypatch.setattr(catalog.get_catalog().settings, "model_mode", mode)


def test_byok_student_without_key_is_told_to_add_one(monkeypatch):
    _mode(monkeypatch, "byok")
    with pytest.raises(llm.ModelUnavailable) as e:
        llm.resolve_for("ravi")
    assert "own AI key" in str(e.value)


def test_byok_student_uses_own_key(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    asyncio.run(keys.put_key(keys.KeyBody(provider="anthropic", key=SECRET_KEY)))
    _mode(monkeypatch, "byok")
    assert llm.resolve_for("ravi").api_key == SECRET_KEY


def test_byok_staff_use_shared_model(monkeypatch):
    _mode(monkeypatch, "byok")
    shared = object()
    monkeypatch.setattr(llm, "_shared_config", lambda: shared)
    assert llm.resolve_for("boss") is shared


def test_shared_mode_prefers_students_own_key(monkeypatch, key_ok):
    as_user(monkeypatch, "ravi")
    asyncio.run(keys.put_key(keys.KeyBody(provider="anthropic", key=SECRET_KEY)))
    monkeypatch.setattr(llm, "_shared_config", lambda: "shared")
    assert llm.resolve_for("ravi").api_key == SECRET_KEY
    assert llm.resolve_for("asha") == "shared"
