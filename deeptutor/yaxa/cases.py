"""Weekly case: one real Indian case per session that Yaxa teaches the session's idea through.

Yaxa drafts a case from the session's readings; faculty edit and approve it (as with session checks).
Learners see an approved case only, never its grasp notes: those tell Yaxa what a learner who has
understood the idea can say, and are used to guide the Learn session and judge explain-back.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import community, store

logger = logging.getLogger(__name__)

MIN_WORDS = 80
MAX_WORDS = 400
MIN_GRASP = 2
MAX_GRASP = 5


class Case(BaseModel):
    module: str
    session: str
    status: Literal["draft", "approved"] = "draft"
    version: int = 1
    title: str = ""
    situation: str = ""
    opening: str = ""  # Yaxa's first question in the Learn session
    grasp: list[str] = Field(default_factory=list)  # staff and model only
    approved_by: str = ""
    approved_at: str = ""


def validate(c: Case) -> list[str]:
    """Plain-language problems that stop a case being saved or approved; empty when fine."""
    problems = []
    if not c.title.strip():
        problems.append("Give the case a title.")
    elif len(c.title) > 120:
        problems.append("Keep the title under 120 characters.")
    n = len(c.situation.split())
    if not MIN_WORDS <= n <= MAX_WORDS:
        problems.append(f"The situation should be {MIN_WORDS}–{MAX_WORDS} words (it is {n}).")
    if not c.opening.strip():
        problems.append("Write the opening question Yaxa asks first.")
    notes = [g for g in c.grasp if g.strip()]
    if not MIN_GRASP <= len(notes) <= MAX_GRASP:
        problems.append(f"List {MIN_GRASP}–{MAX_GRASP} things a learner who understands the idea can say.")
    return problems


def _case_path(module: str, session: str):
    return community.root("cases", store._safe(module)) / f"{store._safe(session)}.json"


def load_case(module: str, session: str) -> Case | None:
    data = store._read_json(_case_path(module, session))
    return Case.model_validate(data) if data else None


def save_case(c: Case) -> None:
    store._write_json(_case_path(c.module, c.session), c.model_dump())


def public_view(c: Case) -> dict[str, Any]:
    """What a learner sees: never the grasp notes."""
    return {"module": c.module, "session": c.session, "version": c.version,
            "title": c.title, "situation": c.situation, "opening": c.opening}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
