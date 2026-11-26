"""Session check: five multiple-choice questions on a session's readings, taken before the webinar.

Faculty approve each set in Yaxa; learners see only approved sets. Every wrong option names the
misconception behind it, so the faculty brief can say what the cohort got wrong, not just a score.
Marking is automatic: the model is used only to draft a set and to suggest uses of live time.

One set per session, shared by all cohorts: ``<data>/yaxa/checks/<MODULE>/<SESSION>.json``.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import community, store
from .access import _me, _privileged, _require_module
from .catalog import get_catalog
from .schedule import learner_cohort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checks")

QUESTIONS = 5
READY = 4  # score out of 5 that marks a learner ready for the session
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


# ------------------------------------------------------------------ learners
class SubmitBody(BaseModel):
    version: int
    answers: dict[str, int]  # question id -> stored option index


def _cohort_code(user: store.YaxaUser) -> str:
    c = learner_cohort(user)
    return c.code if c else "_none"  # attempts without a cohort are kept but never reported


def _attempts_path(cohort: str, module: str, session: str):
    return community.root("checks", "attempts", store._safe(cohort)) / f"{store._safe(module)}__{store._safe(session)}.jsonl"


def _session_unit(module: str, session: str):
    cu, user = _me()
    mod = _require_module(get_catalog(), cu, user, module)
    if not mod or not any(u.id == session for u in mod.units):
        raise HTTPException(404, "No such session in this module")
    return cu, user, mod


def learner_status(user_id: str, module: str, session: str) -> dict[str, Any]:
    """What the module page shows for one session: is there a check, best score, ready."""
    s = load_set(module, session)
    if not s or s.status != "approved":
        return {"available": False, "best": None, "ready": False, "attempts": 0}
    user = store.load_user(user_id)
    rows = [r for r in community.read_jsonl(_attempts_path(_cohort_code(user), module, session)) if r["user_id"] == user_id]
    best = max((r["score"] for r in rows), default=None)
    return {"available": True, "best": best, "ready": best is not None and best >= READY, "attempts": len(rows)}


@router.get("/{module}/{session}")
async def take(module: str, session: str) -> dict[str, Any]:
    cu, _user, _mod = _session_unit(module, session)
    status = learner_status(cu.id, module, session)
    s = load_set(module, session)
    if not status["available"] or not s:
        return status | {"version": 0, "questions": []}
    questions = []
    for q in s.questions:
        opts = [{"i": i, "text": o.text} for i, o in enumerate(q.options)]  # never the answer or the why
        random.shuffle(opts)
        questions.append({"id": q.id, "text": q.text, "reading": q.reading, "options": opts})
    return status | {"version": s.version, "questions": questions}


@router.post("/{module}/{session}")
async def submit(module: str, session: str, body: SubmitBody) -> dict[str, Any]:
    cu, user, _mod = _session_unit(module, session)
    s = load_set(module, session)
    if not s or s.status != "approved":
        raise HTTPException(404, "This session has no check yet")
    if body.version != s.version:
        raise HTTPException(409, "The check was updated since you opened it. Reload to see the new version.")
    if set(body.answers) != {q.id for q in s.questions}:
        raise HTTPException(400, "Answer every question before submitting")
    results = []
    for q in s.questions:
        picked = body.answers[q.id]
        if not 0 <= picked < len(q.options):
            raise HTTPException(400, f"No such option for {q.id}")
        correct = next(i for i, o in enumerate(q.options) if o.correct)
        results.append({
            "id": q.id, "picked": picked, "correct": correct, "right": picked == correct,
            "why_picked": q.options[picked].why, "why_correct": q.options[correct].why, "reading": q.reading,
        })
    score = sum(r["right"] for r in results)
    path = _attempts_path(_cohort_code(user), module, session)
    with community.locked(path):
        earlier = any(r["user_id"] == cu.id and r["answer_version"] == s.answer_version for r in community.read_jsonl(path))
    community.append_jsonl(path, {
        "user_id": cu.id, "version": s.version, "answer_version": s.answer_version, "answers": body.answers,
        "score": score, "first": not earlier, "staff": _privileged(cu, user), "at": community.now_iso(),
    })
    return {"score": score, "ready": score >= READY, "results": results}
