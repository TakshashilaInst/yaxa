"""Simulation rules that need no model: roles, days, the room's lean, shocks, scores.

Kept free of I/O so each rule can be tested on its own; the routes in
``sim/api.py`` call these and the model.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import random
from typing import Any

from .scenario import Role, Scenario, Shock
from .state import Memo, SimRun

IST = timezone(timedelta(hours=5, minutes=30))
LAST_DAY = 5
MAX_TALKS = 2  # actors a student may meet on Day 2
MAX_TALK_TURNS = 6  # student messages per corridor conversation
MAX_INTERVENTIONS = 3  # student turns in the Day 4 meeting

# Six criteria, each scored 1-4, from how Takshashila teaches policy.
RUBRIC: dict[str, dict[str, str]] = {
    "comparative": {
        "label": "Comparative judgement",
        "strong": "Weighs the chosen option against at least one named alternative and says better or worse for whom.",
    },
    "effects": {
        "label": "Effects over intentions",
        "strong": "Names a likely second-order or unintended consequence and how to watch for it.",
    },
    "feasibility": {
        "label": "Political feasibility",
        "strong": "Says who must agree, who can block, and what it would take to bring them along.",
    },
    "fiscal": {
        "label": "Fiscal and economic realism",
        "strong": "Counts costs honestly: leakage, administrative cost, opportunity cost, and who pays.",
    },
    "evidence": {
        "label": "Use of evidence",
        "strong": "Draws on the course readings or on facts that surfaced in the simulation, cited correctly.",
    },
    "role": {
        "label": "Role fidelity",
        "strong": "Argues from the institution's own mandate and keeps within its red lines, or says openly why it crosses one.",
    },
}


def today_ist() -> date:
    return datetime.now(IST).date()


def assign_role(scenario: Scenario, runs: list[SimRun], rng: random.Random | None = None) -> str:
    """A random role among those used least so far in this scenario (balanced across a cohort)."""
    rng = rng or random.Random()
    counts = Counter(r.role for r in runs if r.scenario == scenario.id)
    fewest = min(counts.get(r.id, 0) for r in scenario.roles)
    return rng.choice([r.id for r in scenario.roles if counts.get(r.id, 0) == fewest])


def unlocked_day(run: SimRun, today: date, open_all: bool) -> int:
    """Day N opens on the start date + N-1 (IST), or at once when faculty opened all days."""
    if open_all:
        return LAST_DAY
    elapsed = (today - date.fromisoformat(run.started)).days
    return max(1, min(LAST_DAY, 1 + elapsed))


def room_lean(run: SimRun) -> str | None:
    """The option most of the room backs, counting the student; ties go the student's way."""
    votes = Counter(run.positions.values())
    mine = run.student_option()
    if mine:
        votes[mine] += 1
    if not votes:
        return None
    top = max(votes.values())
    tied = sorted(o for o, n in votes.items() if n == top)
    return mine if mine in tied else tied[0]


def pick_shock(scenario: Scenario, lean: str | None, rng: random.Random | None = None) -> Shock:
    """A shock written for the room's lean; otherwise one that fits any lean."""
    rng = rng or random.Random()
    specific = [s for s in scenario.shocks if lean and lean in s.when]
    return rng.choice(specific or [s for s in scenario.shocks if "any" in s.when] or scenario.shocks)


def initial_positions(scenario: Scenario, student_role: str) -> dict[str, str]:
    return {r.id: (r.leans or scenario.default_option) for r in scenario.roles if r.id != student_role}


def parse_positions(data: dict[str, Any] | None, scenario: Scenario, student_role: str) -> dict[str, str]:
    """{role: option} from a model reply, keeping only real Yaxa-played roles and real options."""
    raw = (data or {}).get("positions") or {}
    options = {o.id for o in scenario.options}
    out = {
        rid: str(opt).strip().upper()[:1]
        for rid, opt in raw.items()
        if scenario.role(rid) and rid != student_role and str(opt).strip().upper()[:1] in options
    }
    if not out:
        raise ValueError("no usable positions in the reply")
    return out


def parse_scores(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """{criterion: {score 1-4, reason}} for every rubric criterion, or ValueError."""
    raw = (data or {}).get("scores") or {}
    out: dict[str, dict[str, Any]] = {}
    for key in RUBRIC:
        item = raw.get(key)
        if not isinstance(item, dict):
            raise ValueError(f"missing score for {key}")
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            raise ValueError(f"bad score for {key}") from None
        out[key] = {"score": max(1, min(4, score)), "reason": str(item.get("reason") or "").strip()}
    return out


def effective_scores(memo: Memo) -> dict[str, int]:
    """The scores that count: a faculty override replaces Yaxa's score."""
    return {k: memo.override.get(k, v["score"]) for k, v in memo.scores.items()}


def _public_role(r: Role) -> dict[str, str]:
    return {"id": r.id, "name": r.name, "mandate": r.mandate}


def _memo_view(m: Memo) -> dict[str, Any]:
    eff = effective_scores(m)
    return m.model_dump(exclude={"override"}) | {
        "scores": {k: v | {"score": eff[k], "overridden": k in m.override} for k, v in m.scores.items()},
        "total": sum(eff.values()),
    }


def public_view(run: SimRun, scenario: Scenario, unlocked: int) -> dict[str, Any]:
    """What the student may see: the shared brief, every role's public face, their own card.

    Other roles' private information, red lines and positions, and the answer key,
    stay on the server. Positions appear only after the run is finished.
    """
    mine = scenario.role(run.role)
    shock = next((s for s in scenario.shocks if s.id == run.shock), None)
    finished = run.stage > LAST_DAY
    run_view = run.model_dump(exclude={"positions", "history", "memos", "user_id"}) | {
        "memos": [_memo_view(m) for m in run.memos],
        "unlocked": unlocked,
    }
    if finished:
        run_view["history"] = run.history
        run_view["positions"] = run.positions
    return {
        "scenario": {
            "id": scenario.id,
            "title": scenario.title,
            "tagline": scenario.tagline,
            "setting": scenario.setting,
            "brief": scenario.brief,
            "decision": scenario.decision,
            "body": scenario.body,
            "decider": scenario.decider,
            "options": [o.model_dump() for o in scenario.options],
            "days": scenario.days,
            "roles": [_public_role(r) for r in scenario.roles],
            "chair": scenario.chair,
        },
        "my_role": mine.model_dump() if mine else None,
        "shock": shock.model_dump() if shock and unlocked >= 3 and run.stage >= 3 else None,
        "rubric": {k: v["label"] for k, v in RUBRIC.items()},
        "run": run_view,
    }
