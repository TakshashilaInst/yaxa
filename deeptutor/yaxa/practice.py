"""Practice mode: Yaxa asks a question on a learning unit, marks the answer, tracks mastery.

A question is written from the unit's own course passages and set in the
student's world where it can be. The marking points stay on the server until
the student has answered, so they can't be read off the page.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import grounding, prompting, store
from .access import _cited_numbers, _me, _public_passage, _require_module, _short, parse_json_reply
from .catalog import Module, Unit, get_catalog
from .llm import ModelUnavailable, complete_text, resolve_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/practice")

PASSAGES = 6  # course passages a question is written from
VERDICTS = {0: "Not yet", 1: "Partly there", 2: "Mostly there", 3: "Got it"}

QUESTION_PROMPT = """\
You write practice questions for a Takshashila public policy course.
Write ONE question that makes the student apply or reason with an idea from the numbered passages,
not recall a definition. Good questions put the idea to work: a choice to analyse, a policy to compare
with its alternative, a trade-off to weigh. Set it in the student's own world when that fits naturally.
The student should be able to answer well in 3 to 6 sentences using the passages' ideas.
Don't repeat or closely paraphrase a previous question.

Reply with JSON only, no other text:
{"question": "<the question, under 70 words>",
 "uses": [<passage numbers the question is built on>],
 "good_answer_covers": ["<a point a good answer makes>", "<2 to 4 points in all>"]}"""

MARKING_PROMPT = """\
You mark a student's answer to a practice question in a Takshashila public policy course.
Judge the reasoning, not the wording. Use the marking points and the numbered passages.
Score: 0 = not yet (misses the main idea), 1 = partly (has the idea but key gaps or an error),
2 = mostly (sound, one point thin or missing), 3 = got it (covers the points with sound reasoning).

Feedback for the student, in Markdown, addressed as "you", under 160 words:
- start with what they got right, specifically;
- then what is missing or shaky, and why it matters;
- cite the passage that covers each missing point with its number in square brackets, e.g. [2];
  use only passage numbers given below;
- end with one short tip for next time.

Reply with JSON only, no other text:
{"score": <0-3>, "feedback": "<markdown>", "missing": ["<a point they didn't make>", "..."]}"""


# ----------------------------------------------------------------- mastery
def unit_status(scores: list[int]) -> str:
    """new → practising → mastered (the last two answers both scored 3)."""
    if not scores:
        return "new"
    if len(scores) >= 2 and min(scores[-2:]) >= 3:
        return "mastered"
    return "practising"


def _progress(user_id: str, module: Module) -> list[dict[str, Any]]:
    answered = [i for i in store.list_practice(user_id, module.code) if i.score is not None]
    out = []
    for u in module.units:
        scores = [i.score for i in answered if i.unit == u.id and i.score is not None]
        out.append(
            {
                "id": u.id,
                "title": u.title,
                "answered": len(scores),
                "last_scores": scores[-5:],
                "status": unit_status(scores),
            }
        )
    return out


def _pick_unit(module: Module, progress: list[dict[str, Any]], wanted: str | None) -> Unit | None:
    """The unit asked for, else the first one not yet mastered."""
    if wanted:
        unit = module.unit(wanted)
        if not unit:
            raise HTTPException(404, "Unknown learning unit")
        return unit
    for row in progress:
        if row["status"] != "mastered":
            return module.unit(row["id"])
    return module.units[0] if module.units else None


# ------------------------------------------------------------------ routes
@router.get("/progress")
async def progress(module: str) -> dict[str, Any]:
    cu, user = _me()
    mod = _require_module(get_catalog(), cu, user, module)
    assert mod is not None
    recent = [
        {"id": i.id, "unit": i.unit, "question": i.question, "score": i.score, "verdict": VERDICTS.get(i.score or 0)}
        for i in store.list_practice(cu.id, mod.code)
        if i.score is not None
    ][-8:]
    return {"module": mod.code, "title": mod.title, "units": _progress(cu.id, mod), "recent": recent[::-1]}


class QuestionBody(BaseModel):
    module: str
    unit: str | None = None


@router.post("/question")
async def new_question(body: QuestionBody) -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    mod = _require_module(cat, cu, user, body.module)
    assert mod is not None
    unit = _pick_unit(mod, _progress(cu.id, mod), body.unit)
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, cat.settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's question limit. It resets tomorrow.")

    topic = f"{unit.title}. {unit.outcomes}" if unit else mod.title
    passages = await grounding.retrieve(mod.kb, topic, PASSAGES, corpus=mod.title) if mod.kb else []
    if not passages:
        raise HTTPException(503, "Yaxa couldn't find course material for this unit yet.")

    asked = [i.question for i in store.list_practice(cu.id, mod.code) if i.unit == (unit.id if unit else None)][-6:]
    context = "\n\n".join(
        part
        for part in (
            prompting._module_block(mod, unit),
            prompting._profile_block(user.profile, user.display_name),
            "Previous questions (don't repeat):\n" + "\n".join(f"- {q}" for q in asked) if asked else "",
            "Course passages:\n\n" + prompting.number_passages(passages),
        )
        if part
    )
    data: dict[str, Any] = {}
    for _attempt in range(2):  # models occasionally return malformed JSON; one retry
        try:
            reply = await complete_text(
                config,
                [{"role": "system", "content": QUESTION_PROMPT}, {"role": "user", "content": context}],
                max_tokens=2000,
            )
        except Exception as exc:
            logger.exception("yaxa practice: question generation failed")
            raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
        data = parse_json_reply(reply) or {}
        if str(data.get("question") or "").strip():
            break
        logger.warning("yaxa practice: unparseable question reply: %s", _short(reply, 300))
    question = str(data.get("question") or "").strip()
    if not question:
        raise HTTPException(502, "Yaxa wrote an unreadable question. Try again.")

    item = store.PracticeItem(
        user_id=cu.id,
        module=mod.code,
        unit=unit.id if unit else None,
        question=question,
        rubric=[str(p) for p in (data.get("good_answer_covers") or [])][:5],
        sources=[_public_passage(p, i) for i, p in enumerate(passages, 1)],
    )
    store.save_practice(item)
    return {"item_id": item.id, "unit": item.unit, "unit_title": unit.title if unit else "", "question": item.question}


class AnswerBody(BaseModel):
    item_id: str
    answer: str


@router.post("/answer")
async def mark_answer(body: AnswerBody) -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    answer = body.answer.strip()
    if len(answer) < 15:
        raise HTTPException(400, "Write a few sentences first.")
    if len(answer) > 5000:
        raise HTTPException(413, "That answer is too long. Keep it under 5,000 characters.")
    item = store.load_practice(cu.id, body.item_id)
    if not item:
        raise HTTPException(404, "Practice question not found")
    if item.score is not None:
        raise HTTPException(409, "You've already answered this one. Ask for a new question.")
    mod = _require_module(cat, cu, user, item.module)
    assert mod is not None
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    passages_block = "\n\n".join(f"[{s['n']}] {s['title']}\n{s['text'].strip()}" for s in item.sources)
    context = (
        f"Question: {item.question}\n\nMarking points:\n"
        + "\n".join(f"- {p}" for p in item.rubric)
        + f"\n\nCourse passages:\n\n{passages_block}\n\nStudent's answer:\n{answer}"
    )
    try:
        reply = await complete_text(
            config,
            [{"role": "system", "content": MARKING_PROMPT}, {"role": "user", "content": context}],
            max_tokens=2000,
        )
    except Exception as exc:
        logger.exception("yaxa practice: marking failed")
        raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
    data = parse_json_reply(reply) or {}
    try:
        score = max(0, min(3, int(data["score"])))
    except (KeyError, TypeError, ValueError):
        logger.warning("yaxa practice: unparseable marking reply: %s", _short(reply, 300))
        raise HTTPException(502, "Yaxa couldn't mark that. Try submitting again.") from None

    item.answer = answer
    item.score = score
    item.feedback = str(data.get("feedback") or "").strip()
    item.missing = [str(m) for m in (data.get("missing") or [])][:5]
    item.citations = [{"n": n, "dangling": not (1 <= n <= len(item.sources))} for n in _cited_numbers(item.feedback)]
    item.answered_at = datetime.now(timezone.utc).isoformat()
    store.save_practice(item)

    unit_row = next((u for u in _progress(cu.id, mod) if u["id"] == item.unit), None)
    return {
        "item_id": item.id,
        "score": score,
        "verdict": VERDICTS[score],
        "feedback": item.feedback,
        "missing": item.missing,
        "marking_points": item.rubric,
        "citations": item.citations,
        "sources": item.sources,
        "unit": unit_row,
    }
