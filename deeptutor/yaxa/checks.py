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

from . import community, grounding, prompting, store
from .access import _me, _privileged, _require_module, _short, parse_json_reply
from .catalog import get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for
from .schedule import learner_cohort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checks")
admin_router = APIRouter(prefix="/checks/admin")  # mounted before `router`, whose /{module}/{session} would match it

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
        problems += question_problems(q, n)
    return problems


def question_problems(q: Question, n: int) -> list[str]:
    problems: list[str] = []
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


# ------------------------------------------------------------------ faculty: draft, edit, approve
PASSAGES = 10

DRAFT_PROMPT = """\
You write a short check that learners in a Takshashila public policy course take before a live session.
Write {n} multiple-choice question(s) from the numbered course passages. Each question tests whether the
learner understood an idea: applying it to a case, telling two ideas apart, or choosing between options.
Never test recall of a definition's wording, a name, or a date.
Each question rests on one passage. Give 3 or 4 options, exactly one correct. Every wrong option must be
something a learner with a specific, common misunderstanding would pick: name that misunderstanding in a
few words (e.g. "Treats the government as the State"). Each option gets a one-line "why": why it is right,
or why it is wrong. Plain text, no markdown.

Reply with JSON only, no other text:
{{"questions": [{{"text": "<question, under 60 words>", "uses": <passage number>,
  "options": [{{"text": "<option>", "correct": true|false, "why": "<one line>",
               "misconception": "<wrong options only: the misunderstanding, under 10 words>"}}]}}]}}"""


class EditBody(BaseModel):
    questions: list[Question]


def _require_staff():
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Session checks are edited by faculty")
    return cu, user


def _module_unit(module: str, session: str):
    mod = get_catalog().module(module)
    unit = next((u for u in mod.units if u.id == session), None) if mod else None
    if not mod or not unit:
        raise HTTPException(404, "No such session in this module")
    return mod, unit


def _staff_name(cu, user) -> str:
    name = (user.display_name or cu.id or "").strip()
    return name.split("@")[0] if "@" in name else name


def _parse_questions(data: dict | None, passages: list[dict], n: int) -> list[Question] | None:
    """The model's questions, or None if any is unusable."""
    raw = (data or {}).get("questions")
    if not isinstance(raw, list) or len(raw) != n:
        return None
    out = []
    for k, q in enumerate(raw, 1):
        try:
            uses = int(q.get("uses") or 0)
            reading = passages[uses - 1].get("file") or passages[uses - 1].get("title", "") if 1 <= uses <= len(passages) else ""
            question = Question(id=f"q{k}", text=str(q.get("text") or "").strip(), reading=reading,
                                options=[Option(text=str(o.get("text") or "").strip(), correct=bool(o.get("correct")),
                                                why=str(o.get("why") or "").strip(),
                                                misconception="" if o.get("correct") else str(o.get("misconception") or "").strip())
                                         for o in q.get("options") or []])
        except (AttributeError, TypeError, ValueError):
            return None
        if question_problems(question, k):
            return None
        out.append(question)
    return out


async def _draft_questions(cu, user, module: str, session: str, n: int, avoid: list[str]) -> list[Question]:
    mod, unit = _module_unit(module, session)
    passages = await grounding.retrieve(mod.kb, f"{unit.title}. {unit.outcomes}", PASSAGES, corpus=mod.title) if mod.kb else []
    if not passages:
        raise HTTPException(503, "Yaxa couldn't find this session's readings in the library yet.")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's limit. It resets tomorrow.")
    context = "\n\n".join(part for part in (
        prompting._module_block(mod, unit),
        "Questions already in this check (don't repeat them):\n" + "\n".join(f"- {t}" for t in avoid) if avoid else "",
        "Course passages:\n\n" + prompting.number_passages(passages),
    ) if part)
    for _attempt in range(2):  # models occasionally return malformed JSON; one retry
        try:
            reply = await complete_text(config, [{"role": "system", "content": DRAFT_PROMPT.format(n=n)},
                                                 {"role": "user", "content": context}], max_tokens=4000)
        except Exception as exc:
            logger.exception("yaxa checks: drafting failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        questions = _parse_questions(parse_json_reply(reply), passages, n)
        if questions:
            return questions
        logger.warning("yaxa checks: unusable draft: %s", _short(reply, 300))
    raise HTTPException(502, "Yaxa's draft didn't follow the rules twice. Try again.")


def _attempt_count(module: str, session: str) -> int:
    base = community.root("checks", "attempts")
    files = base.glob(f"*/{store._safe(module)}__{store._safe(session)}.jsonl") if base.exists() else []
    return sum(len(community.read_jsonl(f)) for f in files)


@admin_router.get("/{module}")
async def admin_list(module: str) -> list[dict[str, Any]]:
    _require_staff()
    mod = get_catalog().module(module)
    if not mod:
        raise HTTPException(404, "Unknown module")
    rows = []
    for u in mod.units:
        s = load_set(module, u.id)
        rows.append({"session": u.id, "title": u.title, "status": s.status if s else "none",
                     "version": s.version if s else 0, "attempts": _attempt_count(module, u.id)})
    return rows


@admin_router.get("/{module}/{session}")
async def admin_get(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    s = load_set(module, session)
    return s.model_dump() if s else {"module": module, "session": session, "status": "none", "questions": []}


@admin_router.post("/{module}/{session}/draft")
async def admin_draft(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    old = load_set(module, session)
    questions = await _draft_questions(cu, user, module, session, QUESTIONS, [])
    s = CheckSet(module=module, session=session, questions=questions,
                 version=(old.version + 1) if old else 1, answer_version=(old.answer_version + 1) if old else 1)
    save_set(s)  # a fresh draft is never live: faculty approve it first
    return s.model_dump()


@admin_router.post("/{module}/{session}/regenerate/{qid}")
async def admin_regenerate(module: str, session: str, qid: str) -> dict[str, Any]:
    cu, user = _require_staff()
    s = load_set(module, session)
    idx = next((i for i, q in enumerate(s.questions) if q.id == qid), None) if s else None
    if s is None or idx is None:
        raise HTTPException(404, "No such question")
    avoid = [q.text for q in s.questions]
    new = (await _draft_questions(cu, user, module, session, 1, avoid))[0]
    new.id = qid
    s.questions[idx] = new
    s.version += 1
    s.answer_version += 1  # a new question: earlier answers to the old one no longer count
    save_set(s)
    return s.model_dump()


@admin_router.put("/{module}/{session}")
async def admin_save(module: str, session: str, body: EditBody) -> dict[str, Any]:
    _require_staff()
    _module_unit(module, session)
    old = load_set(module, session) or CheckSet(module=module, session=session, version=0, answer_version=0)
    s = old.model_copy(update={"questions": body.questions, "version": old.version + 1})
    problems = validate(s)
    if problems:
        raise HTTPException(400, {"problems": problems})
    if answer_key(s) != answer_key(old):
        s.answer_version = old.answer_version + 1
    save_set(s)  # wording fixes keep an approved check approved
    return s.model_dump()


@admin_router.post("/{module}/{session}/approve")
async def admin_approve(module: str, session: str) -> dict[str, Any]:
    cu, user = _require_staff()
    s = load_set(module, session)
    if not s:
        raise HTTPException(404, "Draft the check first")
    problems = validate(s)
    if problems:
        raise HTTPException(400, {"problems": problems})
    s.status, s.approved_by, s.approved_at = "approved", _staff_name(cu, user), community.now_iso()
    save_set(s)
    return s.model_dump()


@admin_router.post("/{module}/{session}/unpublish")
async def admin_unpublish(module: str, session: str) -> dict[str, Any]:
    _require_staff()
    s = load_set(module, session)
    if not s:
        raise HTTPException(404, "No check for this session")
    s.status = "draft"
    save_set(s)
    return s.model_dump()
