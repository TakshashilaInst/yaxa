"""Which model answers a student, and how Yaxa calls it.

Two modes, chosen in content/config.yaml:
  shared   - every student uses one admin profile (the demo: Claude via an API key)
  per_user - each student uses their own ChatGPT/Codex sign-in (real deployment;
             not built yet, so it raises a clear error)

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


def resolve_for(user_id: str) -> LLMConfig:
    settings = get_catalog().settings
    if settings.model_mode != "shared":
        raise ModelUnavailable(
            "Per-student ChatGPT sign-in is not switched on yet. Ask Takshashila to enable it."
        )
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
