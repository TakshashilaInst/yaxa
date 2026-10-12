"""Per-user Yaxa state: learner profile, role, enrolments and conversations.

Plain JSON files under ``<data>/yaxa/``, written atomically (temp file + rename)
so a crash never leaves a half-written file. Fine for a cohort of ~50; swap for
a database when Yaxa outgrows one server.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import uuid

from pydantic import BaseModel, Field

from deeptutor.runtime.home import get_runtime_data_root

# Learner profile fields, in the order the onboarding form asks them.
# Matches the reference prototype, so the demo's sample students carry over.
PROFILE_FIELDS: dict[str, str] = {
    "field": "Your field, in a few words (e.g. AI & education policy)",
    "current_role": "Current role",
    "education": "Education",
    "why_here": "Why are you taking this course?",
    "starting_from": "Where are you starting from?",
    "interests": "Interests",
    "immediate_goal": "What do you want to be able to do soon?",
    "recently_rethinking": "What have you recently been rethinking?",
    "finding_difficult": "What do you find difficult?",
    "questions_exploring": "Questions you're exploring",
    "researching": "What are you working on or researching?",
}
_MAX_FIELD = 1200


class Enrolment(BaseModel):
    programme: str
    track: str | None = None
    cohort: str | None = None


class YaxaUser(BaseModel):
    user_id: str
    display_name: str = ""
    role: str = "student"  # student | faculty
    demo: bool = False  # seeded sample student (can be "entered" from the demo gallery)
    avatar: dict[str, str] = Field(default_factory=dict)  # gallery illustration colours/style
    profile: dict[str, str] = Field(default_factory=dict)
    enrolments: list[Enrolment] = Field(default_factory=list)
    turns_today: int = 0
    turns_day: str = ""

    @property
    def onboarded(self) -> bool:
        return bool(self.profile.get("current_role") or self.profile.get("field"))


def clean_profile(raw: dict[str, Any]) -> dict[str, str]:
    """Keep known fields only, as trimmed strings of bounded length."""
    return {
        k: str(raw.get(k) or "").strip()[:_MAX_FIELD]
        for k in PROFILE_FIELDS
        if str(raw.get(k) or "").strip()
    }


# --------------------------------------------------------------- file helpers
def yaxa_root() -> Path:
    return get_runtime_data_root() / "yaxa"


_SAFE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _safe(part: str) -> str:
    if not _SAFE.match(part or ""):
        raise ValueError(f"unsafe path component: {part!r}")
    return part


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


# ----------------------------------------------------------------------- users
def _user_path(user_id: str) -> Path:
    return yaxa_root() / "users" / f"{_safe(user_id)}.json"


def load_user(user_id: str, display_name: str = "") -> YaxaUser:
    data = _read_json(_user_path(user_id))
    if data:
        return YaxaUser(**data)
    return YaxaUser(user_id=user_id, display_name=display_name)


def save_user(user: YaxaUser) -> None:
    _write_json(_user_path(user.user_id), user.model_dump())


def list_users() -> list[YaxaUser]:
    folder = yaxa_root() / "users"
    if not folder.is_dir():
        return []
    return [YaxaUser(**_read_json(p)) for p in sorted(folder.glob("*.json"))]


def count_turn(user: YaxaUser, limit: int) -> bool:
    """Record one chat turn; False when the user has hit today's limit."""
    today = date.today().isoformat()
    if user.turns_day != today:
        user.turns_day, user.turns_today = today, 0
    if limit and user.turns_today >= limit:
        return False
    user.turns_today += 1
    save_user(user)
    return True


# --------------------------------------------------------------- conversations
class Turn(BaseModel):
    role: str  # user | assistant | system
    content: str
    socratic: bool = False
    faculty: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    module: str | None = None
    unit: str | None = None
    title: str = ""
    turns: list[Turn] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""


def _conv_path(user_id: str, conv_id: str) -> Path:
    return yaxa_root() / "conversations" / _safe(user_id) / f"{_safe(conv_id)}.json"


def load_conversation(user_id: str, conv_id: str) -> Conversation | None:
    data = _read_json(_conv_path(user_id, conv_id))
    return Conversation(**data) if data else None


def save_conversation(conv: Conversation) -> None:
    conv.updated_at = datetime.now(timezone.utc).isoformat()
    _write_json(_conv_path(conv.user_id, conv.id), conv.model_dump())


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    """Newest first; summaries only."""
    folder = yaxa_root() / "conversations" / _safe(user_id)
    if not folder.is_dir():
        return []
    items = []
    for p in folder.glob("*.json"):
        c = _read_json(p) or {}
        items.append(
            {
                "id": c.get("id"),
                "title": c.get("title") or "Untitled",
                "module": c.get("module"),
                "unit": c.get("unit"),
                "updated_at": c.get("updated_at") or c.get("created_at"),
            }
        )
    return sorted(items, key=lambda c: c["updated_at"] or "", reverse=True)
