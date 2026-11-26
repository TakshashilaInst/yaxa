"""Session check: five multiple-choice questions on a session's readings, taken before the webinar.

Faculty approve each set in Yaxa; learners see only approved sets. Every wrong option names the
misconception behind it, so the faculty brief can say what the cohort got wrong, not just a score.
Marking is automatic: the model is used only to draft a set and to suggest uses of live time.

One set per session, shared by all cohorts: ``<data>/yaxa/checks/<MODULE>/<SESSION>.json``.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from . import community, store

logger = logging.getLogger(__name__)

QUESTIONS = 5
MIN_OPTIONS, MAX_OPTIONS = 3, 4


class Option(BaseModel):
    text: str
    correct: bool = False
    why: str = ""  # one line: why this option is right, or why it is wrong
    misconception: str = ""  # wrong options only: the idea a learner who picks it holds


class Question(BaseModel):
    id: str
    text: str
    reading: str = ""  # the library reading the question rests on
    options: list[Option]


class CheckSet(BaseModel):
    module: str
    session: str
    status: Literal["draft", "approved"] = "draft"
    version: int = 1  # bumps on every save
    answer_version: int = 1  # bumps when options or the correct answer change; older attempts stop counting
    approved_by: str = ""
    approved_at: str = ""
    questions: list[Question] = Field(default_factory=list)


def validate(s: CheckSet) -> list[str]:
    """What is wrong with a set, in words faculty can act on; empty when it is fine."""
    problems: list[str] = []
    if len(s.questions) != QUESTIONS:
        problems.append(f"A check needs exactly {QUESTIONS} questions (this one has {len(s.questions)}).")
    for n, q in enumerate(s.questions, 1):
        where = f"Question {n}"
        if not q.text.strip():
            problems.append(f"{where} has no text.")
        if not MIN_OPTIONS <= len(q.options) <= MAX_OPTIONS:
            problems.append(f"{where} needs {MIN_OPTIONS} or {MAX_OPTIONS} options (it has {len(q.options)}).")
        right = [o for o in q.options if o.correct]
        if len(right) != 1:
            problems.append(f"{where} needs exactly one correct option (it has {len(right)}).")
        for m, o in enumerate(q.options, 1):
            if not o.text.strip():
                problems.append(f"{where}, option {m} has no text.")
            if not o.why.strip():
                problems.append(f"{where}, option {m} needs a one-line explanation.")
            if not o.correct and not o.misconception.strip():
                problems.append(f"{where}, option {m} is wrong but doesn't name the misconception behind it.")
    return problems


def _set_path(module: str, session: str):
    return community.root("checks", store._safe(module)) / f"{store._safe(session)}.json"


def load_set(module: str, session: str) -> CheckSet | None:
    raw = store._read_json(_set_path(module, session))
    return CheckSet.model_validate(raw) if raw else None


def save_set(s: CheckSet) -> None:
    community.update_json(_set_path(s.module, s.session), lambda _old: s.model_dump())


def answer_key(s: CheckSet) -> list[tuple[str, ...]]:
    """Per question, its options with the correct one marked: changes when answers change, not wording of questions."""
    return [tuple(("*" if o.correct else "") + o.text.strip() for o in q.options) for q in s.questions]
