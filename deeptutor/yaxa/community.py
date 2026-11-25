"""Shared helpers for cohort life: who sees which cohort, locked files, rate limits.

Announcements, session discussion and cohort chat all live under
``<data>/yaxa/`` as small JSON / JSONL files. Writes take an exclusive lock on a
sidecar ``.lock`` file so two posts at the same moment never lose one another.

A learner always sees their own cohort (any cohort they ask for is ignored).
Faculty and staff pick a cohort. None of this text is indexed or logged.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any

from fastapi import HTTPException

from . import store
from .access import _me, _privileged
from .schedule import Cohort, learner_cohort, load_cohort

EDIT_WINDOW = 15 * 60  # seconds a learner may edit or delete their own post


@dataclass
class Viewer:
    cu: Any
    user: store.YaxaUser
    cohort: Cohort | None
    track: str | None
    staff: bool

    @property
    def uid(self) -> str:
        return self.cu.id

    @property
    def name(self) -> str:
        """The name others see. Never an email address (staff accounts often have one as their name)."""
        name = (self.user.display_name or self.cu.id or "").strip()
        if "@" in name:
            name = re.sub(r"[._-]+", " ", name.split("@")[0]).title()
        return name or "A member"

    def require_cohort(self) -> Cohort:
        if not self.cohort:
            raise HTTPException(404, "You are not in a cohort yet")
        return self.cohort


def viewer(cohort: str | None = None) -> Viewer:
    cu, user = _me()
    staff = _privileged(cu, user)
    c: Cohort | None
    if staff and cohort:
        try:
            c = load_cohort(cohort)
        except ValueError:
            c = None
        if not c:
            raise HTTPException(404, "No such cohort")
    else:
        c = learner_cohort(user)
    track = None
    if c:
        track = next((e.track for e in user.enrolments if e.cohort == c.code), None)
    return Viewer(cu, user, c, track, staff)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return f"{int(time.time() * 1000):x}{secrets.token_hex(3)}"


def age_seconds(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return float("inf")


def root(*parts: str) -> Path:
    return store.yaxa_root().joinpath(*parts)


# ------------------------------------------------------------------ files
_THREAD_LOCK = threading.Lock()  # flock is per-process; this covers threads within one


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK, open(path.with_name(path.name + ".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def append_jsonl(path: Path, row: dict) -> None:
    with locked(path), open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn last line after a crash; skip it
    return out


def rewrite_jsonl(path: Path, fn: Callable[[list[dict]], list[dict]]) -> list[dict]:
    with locked(path):
        rows = fn(read_jsonl(path))
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(path)
        return rows


def update_json(path: Path, fn: Callable[[Any], Any]) -> Any:
    with locked(path):
        data = fn(store._read_json(path))
        store._write_json(path, data)
        return data


# ------------------------------------------------------------------ rate limits
_RATE: dict[tuple[str, str], deque] = {}


def rate_ok(user_id: str, kind: str, limit: int, window: int = 3600) -> bool:
    q = _RATE.setdefault((user_id, kind), deque())
    now = time.monotonic()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def clean_text(text: str, limit: int, what: str = "message") -> str:
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, f"Write a {what} first")
    if len(text) > limit:
        raise HTTPException(400, f"That {what} is too long (limit {limit} characters)")
    return text
