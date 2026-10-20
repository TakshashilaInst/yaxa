"""Shared helpers for Yaxa's routes: who is asking, what they may use, SSE framing.

Kept apart from ``api.py`` so the feature routers (practice, cohort brief,
faculty panel) can use them without importing each other.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from deeptutor.multi_user.context import get_current_user

from . import store
from .catalog import Catalog, Faculty, Module


def _me() -> tuple[Any, store.YaxaUser]:
    cu = get_current_user()
    user = store.load_user(cu.id, display_name=cu.username)
    if not user.display_name:
        user.display_name = cu.username
    return cu, user


def _privileged(cu: Any, user: store.YaxaUser) -> bool:
    return bool(cu.is_admin) or user.role == "faculty"


def _allowed_modules(cat: Catalog, cu: Any, user: store.YaxaUser) -> list[str]:
    if _privileged(cu, user):
        return [code for code, m in cat.modules.items() if m.available]
    codes: list[str] = []
    for e in user.enrolments:
        prog = cat.programme(e.programme)
        if prog:
            codes += [c for c in prog.module_codes(e.track) if c not in codes]
    return codes


def _require_module(cat: Catalog, cu: Any, user: store.YaxaUser, code: str | None) -> Module | None:
    if not code:
        return None
    module = cat.module(code)
    if not module or not module.available:
        raise HTTPException(404, "Module not found or not available yet")
    if code not in _allowed_modules(cat, cu, user):
        raise HTTPException(403, "You are not enrolled in a programme that includes this module")
    return module


def _faculty(cat: Catalog, slug: str | None) -> Faculty | None:
    if not slug:
        return None
    f = cat.faculty.get(slug)
    if not f:
        raise HTTPException(404, "Unknown faculty persona")
    return f


def _short(text: str, n: int = 140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


_CITE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")


def _cited_numbers(answer: str) -> list[int]:
    seen: list[int] = []
    for group in _CITE.findall(answer):
        for n in group.split(","):
            v = int(n)
            if v not in seen:
                seen.append(v)
    return seen


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _public_passage(p: dict[str, Any], n: int) -> dict[str, Any]:
    return {k: p.get(k) for k in ("kb", "file", "title", "unit", "corpus", "kind", "url", "page", "text", "videos", "timestamp", "byline")} | {"n": n}


def parse_json_reply(text: str) -> dict[str, Any] | None:
    """The first JSON object in a model reply (models sometimes wrap it in prose or fences)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1], strict=False)  # allow raw newlines in strings
                    except ValueError:
                        break
                    return value if isinstance(value, dict) else None
        start = text.find("{", start + 1)
    return None
