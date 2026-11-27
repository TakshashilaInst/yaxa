"""Students' own AI keys (Claude or OpenAI), so Takshashila doesn't pay for students' AI use.

A key is tested with a tiny call before it is saved, stored encrypted (Fernet) in a file only the server
reads, and never returned, logged or shown again: the page shows the provider, the model and the last four
characters. The encryption secret comes from YAXA_KEY_SECRET, or is generated once into a 0600 file.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.services.llm.config import LLMConfig

from . import store
from .access import _me
from .catalog import get_catalog

logger = logging.getLogger(__name__)

PROVIDERS = {
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "binding": "anthropic", "api_format": "anthropic"},
    "openai": {"base_url": "https://api.openai.com/v1", "binding": "openai", "api_format": "auto"},
}
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5"}

router = APIRouter(prefix="/me/ai-key")


def _private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _fernet() -> Fernet:
    secret = os.environ.get("YAXA_KEY_SECRET", "").strip()
    if not secret:
        path = store.yaxa_root() / "secrets" / "key-secret"
        if not path.exists():
            _private_write(path, Fernet.generate_key().decode())
        secret = path.read_text().strip()
    return Fernet(secret.encode())


def _path(user_id: str) -> Path:
    return store.yaxa_root() / "keys" / f"{store._safe(user_id)}.json"


def _read(user_id: str) -> dict[str, Any] | None:
    return store._read_json(_path(user_id))


def build_config(provider: str, model: str, key: str) -> LLMConfig:
    p = PROVIDERS[provider]
    return LLMConfig(model=model, api_key=key, base_url=p["base_url"], binding=p["binding"],
                     provider_name=provider, api_format=p["api_format"])


def config_for(user_id: str) -> LLMConfig | None:
    """The student's own model, or None if they haven't added a key (or it can't be decrypted)."""
    row = _read(user_id)
    if not row or row.get("provider") not in PROVIDERS:
        return None
    try:
        key = _fernet().decrypt(row["token"].encode()).decode()
    except (InvalidToken, KeyError, ValueError):
        logger.warning("yaxa keys: a stored key couldn't be decrypted")
        return None
    return build_config(row["provider"], row.get("model") or DEFAULT_MODELS[row["provider"]], key)


def _public(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"provider": None}
    return {"provider": row["provider"], "model": row["model"], "hint": row["hint"], "set_at": row["set_at"]}


# ------------------------------------------------------------------ routes (the student's own key only)
class KeyBody(BaseModel):
    provider: str
    key: str
    model: str = ""


async def complete_text(config, messages, max_tokens=0):  # replaced in tests; late import avoids an llm <-> keys cycle
    from .llm import complete_text as real

    return await real(config, messages, max_tokens=max_tokens)


@router.get("")
async def get_key() -> dict[str, Any]:
    cu, _user = _me()
    return _public(_read(cu.id))


@router.put("")
async def put_key(body: KeyBody) -> dict[str, Any]:
    cu, user = _me()
    provider, key = body.provider.strip().lower(), body.key.strip()
    if provider not in PROVIDERS:
        raise HTTPException(400, "Choose Claude (Anthropic) or OpenAI")
    if len(key) < 20 or len(key) > 400 or any(c.isspace() for c in key):
        raise HTTPException(400, "That doesn't look like an API key")
    model = body.model.strip()[:80] or DEFAULT_MODELS[provider]
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's limit. It resets tomorrow.")
    try:  # one tiny call: a key that doesn't work is never saved
        await complete_text(build_config(provider, model, key),
                            [{"role": "user", "content": "Reply with the word OK."}], max_tokens=5)
    except Exception as exc:  # noqa: BLE001 - the message may echo the key, so only its type is shown
        logger.info("yaxa keys: a key test failed (%s)", type(exc).__name__)
        raise HTTPException(400, f"That key didn't work with {model} ({type(exc).__name__}). Check the key and the model name.") from None
    row = {"provider": provider, "model": model, "hint": f"…{key[-4:]}",
           "token": _fernet().encrypt(key.encode()).decode(), "set_at": datetime.now(timezone.utc).isoformat()}
    _private_write(_path(cu.id), __import__("json").dumps(row))
    return _public(row)


@router.delete("")
async def delete_key() -> dict[str, Any]:
    cu, _user = _me()
    _path(cu.id).unlink(missing_ok=True)
    return {"provider": None}
