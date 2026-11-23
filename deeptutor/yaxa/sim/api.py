"""Simulation routes, mounted at /api/yaxa/sim.

A student plays one role over five days; Yaxa plays the rest. Each day's
action is refused until that day has unlocked (IST date, or faculty opened
all days) and until the previous day is done. Faculty routes list every run,
override rubric scores and open all days for a class.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import grounding, store
from ..access import (
    _allowed_modules,
    _cited_numbers,
    _me,
    _privileged,
    _public_passage,
    _short,
    parse_json_reply,
)
from ..catalog import get_catalog
from ..llm import ModelUnavailable, complete_text, resolve_for
from . import engine, prompts, state
from .scenario import Scenario, get_scenario, load_scenarios

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sim")

PASSAGES = 6
MEMO_MIN, MEMO_MAX = 80, 4000  # characters


# ----------------------------------------------------------------- helpers
def _scenario_for(cu: Any, user: store.YaxaUser, scenario_id: str) -> Scenario:
    s = get_scenario(scenario_id)
    if not s:
        raise HTTPException(404, "Unknown simulation")
    if not _privileged(cu, user) and s.module not in _allowed_modules(get_catalog(), cu, user):
        raise HTTPException(403, "This simulation belongs to a module you are not enrolled in")
    return s


def _load(cu: Any, run_id: str) -> tuple[state.SimRun, Scenario]:
    run = state.load_run(cu.id, run_id)
    if not run:
        raise HTTPException(404, "Simulation run not found")
    s = get_scenario(run.scenario)
    if not s:
        raise HTTPException(404, "This simulation is no longer available")
    return run, s


def _unlocked(run: state.SimRun) -> int:
    return engine.unlocked_day(run, engine.today_ist(), state.open_all(run.scenario))


def _require_day(run: state.SimRun, day: int) -> None:
    if run.stage > engine.LAST_DAY:
        raise HTTPException(409, "This simulation is finished")
    if run.stage != day:
        raise HTTPException(409, f"You are on day {run.stage}, not day {day}")
    if _unlocked(run) < day:
        raise HTTPException(403, f"Day {day} opens tomorrow morning")


def _view(run: state.SimRun, s: Scenario) -> dict[str, Any]:
    return engine.public_view(run, s, _unlocked(run))


def _config(cu: Any, user: store.YaxaUser):
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not store.count_turn(user, get_catalog().settings.daily_turn_limit):
        raise HTTPException(429, "You've reached today's limit. It resets tomorrow.")
    return config


async def _ask(config, system: str, user_text: str, *, max_tokens: int = 1500) -> str:
    try:
        return await complete_text(config, [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
                                   max_tokens=max_tokens)
    except Exception as exc:
        logger.exception("yaxa sim: model call failed")
        raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc


async def _ask_json(config, system: str, user_text: str, parse, *, max_tokens: int = 2000):
    """A JSON reply run through `parse`; one retry, then 502 (and the caller saves nothing)."""
    for _attempt in range(2):
        reply = await _ask(config, system, user_text, max_tokens=max_tokens)
        try:
            return parse(parse_json_reply(reply))
        except (ValueError, TypeError, KeyError):
            logger.warning("yaxa sim: unusable model reply: %s", _short(reply, 200))
    raise HTTPException(502, "Yaxa's reply couldn't be read. Try again.")


async def _passages(s: Scenario, query: str) -> list[dict[str, Any]]:
    return await grounding.retrieve_across(s.libraries, query, PASSAGES)


async def _update_positions(config, s: Scenario, run: state.SimRun, event: str) -> None:
    """Let the game master move Yaxa-played roles; keep the old positions if its reply is unusable."""
    try:
        new = await _ask_json(config, prompts.POSITIONS_SYSTEM, prompts.positions_context(s, run, event),
                              lambda d: engine.parse_positions(d, s, run.role), max_tokens=800)
    except HTTPException:
        logger.warning("yaxa sim: positions unchanged for run %s", run.id)
        return
    run.positions.update(new)


def _snapshot(run: state.SimRun, day: int) -> None:
    run.history.append({"day": day, "positions": dict(run.positions), "student": run.student_option()})


# ------------------------------------------------------------ student routes
@router.get("/scenarios")
async def scenarios() -> list[dict[str, Any]]:
    cu, user = _me()
    cat = get_catalog()
    allowed = set(_allowed_modules(cat, cu, user))
    mine = state.list_runs(user_id=cu.id)
    out = []
    for s in load_scenarios().values():
        if s.module not in allowed and not _privileged(cu, user):
            continue
        mod = cat.module(s.module)
        out.append({
            "id": s.id, "title": s.title, "tagline": s.tagline, "setting": s.setting,
            "module": s.module, "module_title": mod.title if mod else s.module,
            "runs": [{"id": r.id, "stage": r.stage, "role": (s.role(r.role).name if s.role(r.role) else r.role),
                      "started": r.started} for r in mine if r.scenario == s.id],
        })
    return out


class StartBody(BaseModel):
    scenario: str
    force_new: bool = False  # start again after finishing


@router.post("/runs")
async def start(body: StartBody) -> dict[str, Any]:
    cu, user = _me()
    s = _scenario_for(cu, user, body.scenario)
    current = [r for r in state.list_runs(user_id=cu.id, scenario=s.id) if r.stage <= engine.LAST_DAY]
    if current:
        return _view(current[-1], s)
    role = engine.assign_role(s, state.list_runs(scenario=s.id), random.Random())
    cohort = next((e.cohort for e in user.enrolments if e.cohort), None)
    run = state.SimRun(user_id=cu.id, scenario=s.id, role=role, started=engine.today_ist().isoformat(),
                       cohort=cohort, positions=engine.initial_positions(s, role))
    _snapshot(run, 0)
    state.save_run(run)
    return _view(run, s)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    cu, _user = _me()
    run, s = _load(cu, run_id)
    return _view(run, s)


class MemoBody(BaseModel):
    day: Literal[1, 3, 5]
    option: str
    text: str
    stance: Literal["", "concur", "conditions", "dissent"] = ""


@router.post("/runs/{run_id}/memo")
async def memo(run_id: str, body: MemoBody) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    if run.memo(body.day):
        raise HTTPException(409, f"You've already filed your day {body.day} memo")
    _require_day(run, body.day)
    option = body.option.strip().upper()
    if not s.option(option):
        raise HTTPException(400, "Pick one of the options")
    text = body.text.strip()
    if not MEMO_MIN <= len(text) <= MEMO_MAX:
        raise HTTPException(400, f"Write between {MEMO_MIN} and {MEMO_MAX} characters")
    if body.day == 5 and not body.stance:
        raise HTTPException(400, "Say whether you concur with the chair's draft, concur with conditions, or dissent")
    config = _config(cu, user)

    passages = await _passages(s, f"{s.title}. {text}")
    block = prompts.passages_block(passages)
    scored = await _ask_json(
        config, prompts.SCORING_SYSTEM, prompts.scoring_context(s, run, text, option, body.day, block),
        lambda d: (engine.parse_scores(d), str((d or {}).get("feedback") or "").strip()),
    )
    run.memos.append(state.Memo(day=body.day, option=option, text=text, stance=body.stance,
                                scores=scored[0], feedback=scored[1]))

    if body.day == 1:
        await _update_positions(config, s, run, f"The student filed their opening memo backing option {option}:\n{text}")
        _snapshot(run, 1)
        run.stage = 2
    elif body.day == 3:
        await _update_positions(config, s, run, f"After the news, the student revised their memo, backing option {option}:\n{text}")
        _snapshot(run, 3)
        run.stage = 4
    else:
        outcome_passages = await _passages(s, f"{s.title}. {s.decision}")
        result = await _ask_json(
            config, prompts.outcome_system(s), prompts.outcome_context(s, run, prompts.passages_block(outcome_passages)),
            _parse_outcome(s), max_tokens=4000,
        )
        sources = [_public_passage(p, i) for i, p in enumerate(outcome_passages, 1)]
        run.outcome = result | {"sources": sources, "citations": [
            {"n": n, "dangling": not (1 <= n <= len(sources))}
            for n in _cited_numbers(result["consequences"] + result["debrief"])]}
        _snapshot(run, 5)
        run.stage = engine.LAST_DAY + 1
    state.save_run(run)
    return _view(run, s)


def _parse_outcome(s: Scenario):
    def parse(d: dict[str, Any] | None) -> dict[str, str]:
        d = d or {}
        option = str(d.get("option") or "").strip().upper()[:1]
        if not s.option(option) or not str(d.get("debrief") or "").strip():
            raise ValueError("outcome without option or debrief")
        return {k: str(d.get(k) or "").strip() for k in ("decision", "consequences", "debrief")} | {"option": option}
    return parse


class TalkBody(BaseModel):
    role: str
    message: str = Field(max_length=2000)


@router.post("/runs/{run_id}/talk")
async def talk(run_id: str, body: TalkBody) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    _require_day(run, 2)
    actor = s.role(body.role)
    if not actor or actor.id == run.role:
        raise HTTPException(400, "Pick another member to meet")
    convo = next((t for t in run.talks if t.role == actor.id), None)
    if not convo and len(run.talks) >= engine.MAX_TALKS:
        raise HTTPException(409, f"You can meet {engine.MAX_TALKS} members on day 2")
    if convo and sum(t["who"] == "student" for t in convo.turns) >= engine.MAX_TALK_TURNS:
        raise HTTPException(409, "That meeting is over. Finish the day when you're ready.")
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Say something first")
    config = _config(cu, user)

    passages = await _passages(s, f"{actor.name}. {message}")
    system = prompts.actor_system(s, actor, run, student_role=s.role(run.role))
    history = [{"role": "user" if t["who"] == "student" else "assistant", "content": t["content"]}
               for t in (convo.turns if convo else [])]
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": f"{message}\n\n---\nCourse passages you may cite:\n\n{prompts.passages_block(passages) or '(none)'}"}]
    try:
        reply = (await complete_text(config, messages, max_tokens=800)).strip()
    except Exception as exc:
        logger.exception("yaxa sim: actor reply failed")
        raise HTTPException(502, f"Yaxa couldn't reach its model: {type(exc).__name__}") from exc
    sources = [_public_passage(p, i) for i, p in enumerate(passages, 1)]
    citations = [{"n": n, "dangling": not (1 <= n <= len(sources))} for n in _cited_numbers(reply)]
    if not convo:
        convo = state.Talk(role=actor.id)
        run.talks.append(convo)
    convo.turns.append({"who": "student", "content": message})
    convo.turns.append({"who": "actor", "content": reply, "sources": sources, "citations": citations})
    state.save_run(run)
    return {"reply": reply, "sources": sources, "citations": citations, "turns_left": engine.MAX_TALK_TURNS - sum(
        t["who"] == "student" for t in convo.turns)}


@router.post("/runs/{run_id}/talks/done")
async def finish_talks(run_id: str) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    _require_day(run, 2)
    if not run.talks:
        raise HTTPException(400, "Meet at least one member first")
    config = _config(cu, user)
    summary = "\n\n".join(
        f"Talk with {t.role}:\n" + "\n".join(f"{x['who']}: {x['content']}" for x in t.turns) for t in run.talks)
    await _update_positions(config, s, run, f"The student held private talks:\n{summary}")
    run.shock = engine.pick_shock(s, engine.room_lean(run), random.Random()).id
    _snapshot(run, 2)
    run.stage = 3
    state.save_run(run)
    return _view(run, s)


@router.post("/runs/{run_id}/meeting/open")
async def meeting_open(run_id: str) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    _require_day(run, 4)
    if run.meeting:
        return _view(run, s)
    config = _config(cu, user)
    text = await _ask(config, prompts.meeting_system(s), prompts.meeting_context(s, run, "open"), max_tokens=2500)
    turns = engine.parse_transcript(text)
    if not turns:
        raise HTTPException(502, "Yaxa couldn't write the meeting. Try again.")
    run.meeting = turns
    state.save_run(run)
    return _view(run, s)


class InterveneBody(BaseModel):
    text: str = Field(max_length=2000)


@router.post("/runs/{run_id}/meeting/intervene")
async def meeting_intervene(run_id: str, body: InterveneBody) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    _require_day(run, 4)
    if not run.meeting:
        raise HTTPException(409, "Open the meeting first")
    if run.interventions >= engine.MAX_INTERVENTIONS:
        raise HTTPException(409, f"You've used your {engine.MAX_INTERVENTIONS} interventions")
    said = body.text.strip()
    if len(said) < 10:
        raise HTTPException(400, "Say a little more")
    config = _config(cu, user)
    text = await _ask(config, prompts.meeting_system(s), prompts.meeting_context(s, run, "continue", said), max_tokens=1500)
    me = s.role(run.role)
    run.meeting.append({"speaker": me.name if me else run.role, "text": said, "student": "1"})
    run.meeting += engine.parse_transcript(text)
    run.interventions += 1
    state.save_run(run)
    return _view(run, s)


@router.post("/runs/{run_id}/meeting/close")
async def meeting_close(run_id: str) -> dict[str, Any]:
    cu, user = _me()
    run, s = _load(cu, run_id)
    _require_day(run, 4)
    if not run.meeting:
        raise HTTPException(409, "Open the meeting first")
    config = _config(cu, user)

    def parse(d: dict[str, Any] | None) -> dict[str, str]:
        d = d or {}
        option = str(d.get("option") or "").strip().upper()[:1]
        if not s.option(option) or not str(d.get("text") or "").strip():
            raise ValueError("draft without option or text")
        return {"option": option, "text": str(d["text"]).strip(), "closing": str(d.get("closing") or "").strip()}

    draft = await _ask_json(config, prompts.meeting_system(s), prompts.meeting_context(s, run, "close"), parse)
    chair = s.role(s.chair)
    if draft["closing"]:
        run.meeting.append({"speaker": chair.name if chair else "Chair", "text": draft["closing"]})
    run.draft = {"option": draft["option"], "text": draft["text"]}
    _snapshot(run, 4)
    run.stage = 5
    state.save_run(run)
    return _view(run, s)


# ------------------------------------------------------------ faculty routes
def _require_staff() -> tuple[Any, store.YaxaUser]:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "This page is for faculty")
    return cu, user


@router.get("/faculty/runs")
async def faculty_runs(scenario: str) -> dict[str, Any]:
    _require_staff()
    s = get_scenario(scenario)
    if not s:
        raise HTTPException(404, "Unknown simulation")
    rows = []
    for run in state.list_runs(scenario=s.id):
        student = store.load_user(run.user_id)
        role = s.role(run.role)
        rows.append({
            "user_id": run.user_id, "run_id": run.id, "student": student.display_name or run.user_id,
            "cohort": run.cohort, "role": run.role, "role_name": role.name if role else run.role,
            "stage": run.stage, "started": run.started, "history": run.history,
            "memos": [engine._memo_view(m) | {"override": m.override} for m in run.memos],
            "draft": run.draft, "outcome_option": run.outcome.get("option"),
        })
    return {
        "scenario": {"id": s.id, "title": s.title, "options": [o.model_dump() for o in s.options],
                     "roles": [{"id": r.id, "name": r.name} for r in s.roles], "answer_key": s.answer_key},
        "rubric": {k: v["label"] for k, v in engine.RUBRIC.items()},
        "open_all": state.open_all(s.id),
        "runs": rows,
    }


class OverrideBody(BaseModel):
    user_id: str
    run_id: str
    day: int
    scores: dict[str, int]  # criterion -> 1-4; 0 removes an override


@router.put("/faculty/scores")
async def faculty_override(body: OverrideBody) -> dict[str, Any]:
    _require_staff()
    run = state.load_run(body.user_id, body.run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    m = run.memo(body.day)
    if not m or not m.scores:
        raise HTTPException(400, "There is no scored memo for that day")
    for key, value in body.scores.items():
        if key not in engine.RUBRIC or not 0 <= value <= 4:
            raise HTTPException(400, f"Unknown criterion or score: {key}={value}")
        if value == 0:
            m.override.pop(key, None)
        else:
            m.override[key] = value
    state.save_run(run)
    return engine._memo_view(m) | {"override": m.override}


class SettingsBody(BaseModel):
    scenario: str
    open_all: bool


@router.put("/faculty/settings")
async def faculty_settings(body: SettingsBody) -> dict[str, Any]:
    _require_staff()
    if not get_scenario(body.scenario):
        raise HTTPException(404, "Unknown simulation")
    state.set_open_all(body.scenario, body.open_all)
    return {"scenario": body.scenario, "open_all": body.open_all}
