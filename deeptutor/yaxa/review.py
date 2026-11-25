"""Spaced review for practice mode, using DeepTutor's retention scheduler.

Each learning unit is one item to remember. Its schedule is rebuilt from the
student's marked practice answers, oldest first, by replaying them through
DeepTutor's SpacedRepetitionScheduler (deeptutor/learning/scheduler.py). So
there is nothing extra to store or migrate, and practice done before this
feature existed counts from day one.

Practice marks map to review quality: 0 not yet -> a lapse (comes back soon),
1 partly -> still a lapse, 2 mostly -> a weak pass, 3 got it -> a strong pass.
Policy ideas are concepts, so units use the CONCEPT intervals (3, 7, 14, 30 days).
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from deeptutor.learning.models import KnowledgeType, LearningEvidence, RepetitionState
from deeptutor.learning.scheduler import SpacedRepetitionScheduler

from . import store
from .catalog import Module

KIND = KnowledgeType.CONCEPT
QUALITY = {0: 0.0, 1: 0.35, 2: 0.7, 3: 1.0}
RESULT = {0: "incorrect", 1: "partial", 2: "partial", 3: "correct"}
DAY = 86400

_scheduler = SpacedRepetitionScheduler()


def _ts(item: store.PracticeItem) -> float:
    raw = item.answered_at or item.created_at
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def schedule(items: list[store.PracticeItem]) -> RepetitionState | None:
    """The unit's retention state after replaying its marked answers, or None if none are marked."""
    marked = sorted((i for i in items if i.score is not None), key=_ts)
    if not marked:
        return None
    state = _scheduler.get_initial_state(KIND, now=_ts(marked[0]))
    for item in marked:
        score = max(0, min(3, int(item.score or 0)))
        evidence = LearningEvidence(
            knowledge_point_id=item.unit or "",
            question_id=item.id,
            timestamp=_ts(item),
            source="yaxa_practice",
            assessment_type="qualitative",
            result=RESULT[score],  # type: ignore[arg-type]
            quality=QUALITY[score],
        )
        state = _scheduler.schedule_review(state, KIND, evidence)
    return state


def unit_review(items: list[store.PracticeItem], *, now: float | None = None) -> dict[str, Any] | None:
    """{due, next_review (date), recall (0-1)} for one unit, or None if never practised."""
    state = schedule(items)
    if state is None:
        return None
    moment = time.time() if now is None else now
    return {
        "due": state.next_review_at <= moment,
        "next_review": datetime.fromtimestamp(state.next_review_at, timezone.utc).date().isoformat(),
        "next_review_at": state.next_review_at,
        "recall": round(_scheduler.retrievability(state, now=moment), 2),
    }


def due_units(user_id: str, modules: list[Module], *, now: float | None = None) -> list[dict[str, Any]]:
    """Units due for review across the given modules, most overdue first."""
    moment = time.time() if now is None else now
    out: list[dict[str, Any]] = []
    for mod in modules:
        items = store.list_practice(user_id, mod.code)
        for unit in mod.units:
            info = unit_review([i for i in items if i.unit == unit.id], now=moment)
            if not info or not info["due"]:
                continue
            out.append(
                {
                    "module": mod.code,
                    "module_title": mod.title,
                    "unit": unit.id,
                    "unit_title": unit.title,
                    "recall": info["recall"],
                    "days_overdue": round((moment - info["next_review_at"]) / DAY, 1),
                }
            )
    out.sort(key=lambda d: -d["days_overdue"])
    return out
