"""Which model answers a student, and how Yaxa calls it.

Modes, chosen in content/config.yaml:
  shared   - everyone uses one admin profile (the demo), unless a student added their own key
  byok     - students use their own Claude/OpenAI key (keys.py); staff use the shared profile
  per_user - each student's ChatGPT/Codex sign-in (not built; raises a clear error)

All model access goes through ``resolve_for`` so switching modes later touches
one function.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any

from deeptutor.multi_user.model_access import admin_catalog, is_owner_bound
from deeptutor.services.config.provider_runtime import resolve_llm_runtime_config
from deeptutor.services.llm import factory
from deeptutor.services.llm.config import (
    LLMConfig,
    reset_scoped_llm_config,
    set_scoped_llm_config,
)
from deeptutor.services.model_selection.runtime import llm_config_from_resolved

from .catalog import get_catalog


class ModelUnavailable(RuntimeError):
    """No model is configured for this user; the message is shown to them."""


def _find_shared_selection(catalog: dict[str, Any], wanted_profile: str, wanted_model: str):
    """Pick (profile_id, model entry id) for the shared model from the admin catalog."""
    profiles = catalog.get("services", {}).get("llm", {}).get("profiles", []) or []
    for profile in profiles:
        if is_owner_bound(profile):
            continue  # personal sign-ins (Codex etc.) are never shared
        if wanted_profile and profile.get("id") != wanted_profile:
            continue
        for model in profile.get("models", []) or []:
            if wanted_model in (model.get("id"), model.get("model")):
                return str(profile["id"]), str(model["id"])
    return None


def _staff_ids() -> set[str]:
    from .cohort import _staff_ids as staff  # noqa: PLC0415 - cohort imports llm

    return staff()


def _shared_config() -> LLMConfig:
    settings = get_catalog().settings
    wanted = settings.shared_model or {}
    catalog = admin_catalog()
    picked = _find_shared_selection(
        catalog, wanted.get("profile_id", ""), wanted.get("model", "")
    )
    if not picked:
        raise ModelUnavailable(
            "Yaxa's model isn't set up yet. An admin needs to add the "
            f"'{wanted.get('model', '?')}' model under Settings → Models."
        )
    profile_id, model_id = picked
    resolved = resolve_llm_runtime_config(
        catalog, llm_selection={"profile_id": profile_id, "model_id": model_id}
    )
    return llm_config_from_resolved(resolved)


def resolve_for(user_id: str) -> LLMConfig:
    """shared: everyone on the shared model, except students who added their own key.
    byok: students must use their own key; faculty and admins stay on the shared model."""
    from . import keys  # noqa: PLC0415 - keys imports llm's helpers late too

    mode = get_catalog().settings.model_mode
    if mode not in ("shared", "byok"):
        raise ModelUnavailable(
            "Per-student ChatGPT sign-in is not switched on yet. Ask Takshashila to enable it."
        )
    if mode == "byok" and user_id in _staff_ids():
        return _shared_config()
    own = keys.config_for(user_id)
    if own:
        return own
    if mode == "byok":
        raise ModelUnavailable(
            "Add your own AI key (Claude or OpenAI) under Profile → Your AI key. "
            "Yaxa uses it for your questions; Takshashila doesn't pay for students' AI use."
        )
    return _shared_config()


@contextmanager
def _scoped(config: LLMConfig):
    token = set_scoped_llm_config(config)
    try:
        yield
    finally:
        reset_scoped_llm_config(token)


async def stream_text(
    config: LLMConfig, messages: list[dict[str, Any]], max_tokens: int = 1800
) -> AsyncIterator[str]:
    """Stream answer text, dropping any <think> reasoning blocks."""
    with _scoped(config):
        in_think = False
        async for chunk in factory.stream(prompt="", messages=messages, max_tokens=max_tokens):
            if chunk == "<think>":
                in_think = True
                continue
            if chunk == "</think>":
                in_think = False
                continue
            if not in_think:
                yield chunk


async def complete_text(
    config: LLMConfig, messages: list[dict[str, Any]], max_tokens: int = 1500
) -> str:
    with _scoped(config):
        return await factory.complete(prompt="", messages=messages, max_tokens=max_tokens)
