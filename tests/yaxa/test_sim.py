"""Yaxa simulations: scenarios, run state, engine logic, prompts and routes."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog
from deeptutor.yaxa.sim import scenario as sc


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    sc.load_scenarios.cache_clear()
    yield
    catalog.get_catalog(fresh=True)
    sc.load_scenarios.cache_clear()


# --------------------------------------------------------------- scenarios
def test_both_scenarios_load_with_six_roles_and_four_options() -> None:
    scenarios = sc.load_scenarios()
    assert {"chokepoint", "running-dry"} <= set(scenarios)
    for s in scenarios.values():
        assert len(s.roles) == 6, s.id
        assert [o.id for o in s.options] == ["A", "B", "C", "D"], s.id
        assert s.default_option in {o.id for o in s.options}
        assert s.chair in {r.id for r in s.roles}
        assert s.brief.strip() and s.answer_key.strip() and s.decision.strip()
        for r in s.roles:
            assert r.private.strip() and r.red_line.strip() and r.batna.strip(), (s.id, r.id)


def test_shocks_cover_every_lean() -> None:
    for s in sc.load_scenarios().values():
        options = {o.id for o in s.options}
        for shock in s.shocks:
            assert set(shock.when) <= options | {"any"}, (s.id, shock.id)
        for o in options:
            assert any(o in sh.when or "any" in sh.when for sh in s.shocks), (s.id, o)


def test_scenarios_point_at_real_modules_and_libraries() -> None:
    cat = catalog.get_catalog()
    known_kbs = {m.kb for m in cat.modules.values() if m.kb} | {f.kb for f in cat.faculty.values() if f.kb}
    for s in sc.load_scenarios().values():
        assert cat.module(s.module), s.module
        assert s.libraries and set(s.libraries) <= known_kbs, (s.id, s.libraries)


def test_unknown_scenario_is_none() -> None:
    assert sc.get_scenario("nope") is None
    assert sc.get_scenario("running-dry").title == "Running Dry"


# --------------------------------------------------------------- run state
from datetime import date  # noqa: E402
import random  # noqa: E402

from deeptutor.yaxa.sim import engine, prompts, state  # noqa: E402


def _run(**kw) -> state.SimRun:
    base = {"user_id": "u1", "scenario": "running-dry", "role": "finance", "started": "2026-11-23"}
    return state.SimRun(**(base | kw))


def test_run_round_trip_and_listing() -> None:
    a, b = _run(), _run(user_id="u2", scenario="chokepoint", role="mea")
    state.save_run(a)
    state.save_run(b)
    assert state.load_run("u1", a.id).role == "finance"
    assert state.load_run("u1", "missing") is None
    assert [r.id for r in state.list_runs(user_id="u2")] == [b.id]
    assert [r.id for r in state.list_runs(scenario="running-dry")] == [a.id]
    assert len(state.list_runs()) == 2


def test_open_all_setting_per_scenario() -> None:
    assert state.open_all("running-dry") is False
    state.set_open_all("running-dry", True)
    assert state.open_all("running-dry") is True and state.open_all("chokepoint") is False


# ------------------------------------------------------------------ engine
def test_roles_are_balanced_across_a_cohort() -> None:
    s = sc.get_scenario("running-dry")
    runs: list[state.SimRun] = []
    rng = random.Random(1)
    for i in range(12):
        role = engine.assign_role(s, runs, rng)
        runs.append(_run(user_id=f"u{i}", role=role))
    counts = {r.id: sum(x.role == r.id for x in runs) for r in s.roles}
    assert set(counts.values()) == {2}


def test_days_unlock_by_ist_date_unless_opened() -> None:
    run = _run(started="2026-11-23")
    assert engine.unlocked_day(run, date(2026, 11, 23), False) == 1
    assert engine.unlocked_day(run, date(2026, 11, 25), False) == 3
    assert engine.unlocked_day(run, date(2026, 12, 30), False) == 5
    assert engine.unlocked_day(run, date(2026, 11, 23), True) == 5


def test_room_lean_counts_the_student_and_breaks_ties_their_way() -> None:
    run = _run(positions={"discom": "A", "agriculture": "B", "cmo": "B", "union": "A", "water": "C"})
    run.memos.append(state.Memo(day=1, option="A", text="x"))
    assert engine.room_lean(run) == "A"  # A: 3 (with student), B: 2
    run.memos[-1].option = "C"
    assert engine.room_lean(run) == "C"  # A, B and C tie at 2: the student's option wins


def test_shock_matches_the_lean() -> None:
    s = sc.get_scenario("running-dry")
    rng = random.Random(0)
    assert engine.pick_shock(s, "A", rng).id == "transplanting-cuts"
    assert engine.pick_shock(s, "C", rng).id == "night-meters"


def test_scores_are_clamped_and_must_cover_every_criterion() -> None:
    data = {"scores": {c: {"score": 9, "reason": "r"} for c in engine.RUBRIC}}
    scores = engine.parse_scores(data)
    assert set(scores) == set(engine.RUBRIC) and all(v["score"] == 4 for v in scores.values())
    data["scores"].pop(next(iter(engine.RUBRIC)))
    with pytest.raises(ValueError):
        engine.parse_scores(data)


def test_faculty_override_wins() -> None:
    memo = state.Memo(day=1, option="A", text="x", scores={c: {"score": 2, "reason": "r"} for c in engine.RUBRIC})
    first = next(iter(engine.RUBRIC))
    memo.override = {first: 4}
    eff = engine.effective_scores(memo)
    assert eff[first] == 4 and sum(eff.values()) == 4 + 2 * (len(engine.RUBRIC) - 1)


def test_public_view_hides_other_cards_and_the_answer_key() -> None:
    s = sc.get_scenario("running-dry")
    run = _run(role="finance", positions={"discom": "A"})
    view = engine.public_view(run, s, unlocked=5)
    text = str(view)
    assert s.role("finance").private in text  # your own card
    for r in s.roles:
        if r.id != "finance":
            assert r.private not in text and r.red_line not in text
    assert s.answer_key not in text
    assert "positions" not in view["run"]  # where the others stand is for the debrief


def test_public_view_hides_the_shock_until_day_three() -> None:
    s = sc.get_scenario("running-dry")
    run = _run(stage=3, shock="late-monsoon")
    assert engine.public_view(run, s, unlocked=2)["shock"] is None
    assert engine.public_view(run, s, unlocked=3)["shock"]["id"] == "late-monsoon"


# ----------------------------------------------------------------- prompts
def test_actor_prompt_has_its_own_card_only() -> None:
    s = sc.get_scenario("chokepoint")
    run = _run(scenario="chokepoint", role="mea", positions={"meity": "A"})
    text = prompts.actor_system(s, s.role("meity"), run, student_role=s.role("mea"))
    assert s.role("meity").private in text
    for r in s.roles:
        if r.id != "meity":
            assert r.private not in text
    assert s.answer_key not in text


def test_debrief_prompt_has_answer_key_and_every_card() -> None:
    s = sc.get_scenario("running-dry")
    text = prompts.outcome_system(s)
    assert "Punjab" in text or s.answer_key in text
    run = _run()
    ctx = prompts.outcome_context(s, run)
    for r in s.roles:
        assert r.private in ctx


# ------------------------------------------------------------------ routes
import asyncio  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from deeptutor.yaxa import store  # noqa: E402
from deeptutor.yaxa.sim import api as sim_api  # noqa: E402


def test_transcript_parsing() -> None:
    text = "**Chair:** Let us begin.\n\n**Finance Department:** The deficit\nis tight.\nnoise"
    turns = engine.parse_transcript(text)
    assert turns == [
        {"speaker": "Chair", "text": "Let us begin."},
        {"speaker": "Finance Department", "text": "The deficit\nis tight.\nnoise"},
    ]


class FakeModel:
    """Answers each kind of simulation call by looking at its system prompt."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bad_scores = 0  # how many scoring replies to garble first

    async def __call__(self, config, messages, **kw) -> str:
        system = messages[0]["content"]
        if "score a student's memo" in system:
            self.calls.append("score")
            if self.bad_scores:
                self.bad_scores -= 1
                return "not json"
            return json.dumps({"scores": {c: {"score": 3, "reason": "ok"} for c in engine.RUBRIC}, "feedback": "Good."})
        if "game master" in system:
            self.calls.append("positions")
            return json.dumps({"positions": {"discom": "B", "union": "A"}, "note": "DISCOM moved."})
        if "transcript of a meeting" in system:
            user = messages[-1]["content"]
            if "Reply with JSON only" in user:
                self.calls.append("close")
                return json.dumps({"option": "B", "text": "Recommend B with a pilot.", "closing": "Thank you."})
            self.calls.append("meeting")
            return "**Chief Minister's Office:** We begin.\n\n**DISCOM:** Pay us first."
        if "You close a Takshashila policy simulation" in system:
            self.calls.append("outcome")
            return json.dumps({"option": "B", "decision": "B, piloted.", "consequences": "Uptake grows [1].", "debrief": "## What you traded\n..."})
        self.calls.append("actor")
        return "We can talk, if you pay us in advance [1]."


@pytest.fixture
def sim_env(monkeypatch: pytest.MonkeyPatch):
    model = FakeModel()
    who = {"id": "stu1", "admin": False, "role": "student"}

    def fake_me():
        user = store.load_user(who["id"], display_name="Stu")
        user.role = who["role"]
        user.enrolments = [store.Enrolment(programme="GCPP", track="TP", cohort="TP27")]
        return SimpleNamespace(id=who["id"], is_admin=who["admin"], username="stu"), user

    async def no_passages(kbs, query, k):
        return [{"kb": "GCPP-ER1", "file": "f.pdf", "title": "Reading", "text": "A passage about subsidies. " * 5, "score": 0.5}]

    monkeypatch.setattr(sim_api, "_me", fake_me)
    monkeypatch.setattr(sim_api, "complete_text", model)
    monkeypatch.setattr(sim_api, "resolve_for", lambda uid: object())
    monkeypatch.setattr(sim_api.grounding, "retrieve_across", no_passages)
    monkeypatch.setattr(sim_api.engine, "assign_role", lambda s, runs, rng=None: "finance")
    return SimpleNamespace(model=model, who=who)


def _go(coro):
    return asyncio.run(coro)


def test_full_run_through_five_days(sim_env) -> None:
    state.set_open_all("running-dry", True)
    view = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    rid = view["run"]["id"]
    assert view["my_role"]["id"] == "finance" and view["run"]["stage"] == 1

    view = _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Cap it. " * 20)))
    assert view["run"]["stage"] == 2 and view["run"]["memos"][0]["total"] == 18

    reply = _go(sim_api.talk(rid, sim_api.TalkBody(role="discom", message="What would it take?")))
    assert "advance" in reply["reply"] and reply["sources"]
    view = _go(sim_api.finish_talks(rid))
    assert view["run"]["stage"] == 3 and view["shock"] is not None

    view = _go(sim_api.memo(rid, sim_api.MemoBody(day=3, option="B", text="Revised. " * 20)))
    assert view["run"]["stage"] == 4

    view = _go(sim_api.meeting_open(rid))
    assert view["run"]["meeting"][0]["speaker"] == "Chief Minister's Office"
    view = _go(sim_api.meeting_intervene(rid, sim_api.InterveneBody(text="Finance can fund a pilot.")))
    assert any(t["speaker"] == "Finance Department" for t in view["run"]["meeting"])
    view = _go(sim_api.meeting_close(rid))
    assert view["run"]["stage"] == 5 and view["run"]["draft"]["option"] == "B"

    view = _go(sim_api.memo(rid, sim_api.MemoBody(day=5, option="B", text="Concur. " * 20, stance="conditions")))
    assert view["run"]["stage"] == 6
    assert view["run"]["outcome"]["option"] == "B" and "What you traded" in view["run"]["outcome"]["debrief"]
    assert view["run"]["positions"]  # revealed once finished


def test_locked_day_and_double_memo_are_refused(sim_env) -> None:
    view = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    rid = view["run"]["id"]
    _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Cap it. " * 20)))
    with pytest.raises(HTTPException) as e:
        _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Again. " * 20)))
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:  # Day 2 opens tomorrow
        _go(sim_api.talk(rid, sim_api.TalkBody(role="discom", message="Hello")))
    assert e.value.status_code == 403


def test_garbled_score_retries_then_fails_without_saving(sim_env) -> None:
    view = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    rid = view["run"]["id"]
    sim_env.model.bad_scores = 1
    view = _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Cap it. " * 20)))
    assert view["run"]["stage"] == 2  # one retry was enough
    run2 = _go(sim_api.start(sim_api.StartBody(scenario="chokepoint", force_new=False)))
    sim_env.model.bad_scores = 2
    with pytest.raises(HTTPException) as e:
        _go(sim_api.memo(run2["run"]["id"], sim_api.MemoBody(day=1, option="A", text="Align. " * 20)))
    assert e.value.status_code == 502
    assert state.load_run("stu1", run2["run"]["id"]).memos == []


def test_start_resumes_an_unfinished_run(sim_env) -> None:
    a = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    b = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    assert a["run"]["id"] == b["run"]["id"]


def test_student_view_never_carries_other_private_cards(sim_env) -> None:
    s = sc.get_scenario("running-dry")
    view = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))
    text = json.dumps(_go(sim_api.get_run(view["run"]["id"])))
    for r in s.roles:
        if r.id != "finance":
            assert json.dumps(r.private)[1:-1] not in text


def test_talk_rules(sim_env) -> None:
    state.set_open_all("running-dry", True)
    rid = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))["run"]["id"]
    _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Cap it. " * 20)))
    with pytest.raises(HTTPException) as e:
        _go(sim_api.talk(rid, sim_api.TalkBody(role="finance", message="Me?")))  # your own role
    assert e.value.status_code == 400
    _go(sim_api.talk(rid, sim_api.TalkBody(role="discom", message="Hi")))
    _go(sim_api.talk(rid, sim_api.TalkBody(role="union", message="Hi")))
    with pytest.raises(HTTPException) as e:
        _go(sim_api.talk(rid, sim_api.TalkBody(role="water", message="Hi")))  # a third actor
    assert e.value.status_code == 409


def test_faculty_routes(sim_env) -> None:
    rid = _go(sim_api.start(sim_api.StartBody(scenario="running-dry")))["run"]["id"]
    _go(sim_api.memo(rid, sim_api.MemoBody(day=1, option="C", text="Cap it. " * 20)))
    with pytest.raises(HTTPException) as e:
        _go(sim_api.faculty_runs("running-dry"))
    assert e.value.status_code == 403

    sim_env.who.update(id="fac1", role="faculty")
    rows = _go(sim_api.faculty_runs("running-dry"))
    assert len(rows["runs"]) == 1 and rows["runs"][0]["role"] == "finance"
    assert rows["runs"][0]["memos"][0]["total"] == 18

    body = sim_api.OverrideBody(user_id="stu1", run_id=rid, day=1, scores={"fiscal": 1})
    _go(sim_api.faculty_override(body))
    assert state.load_run("stu1", rid).memo(1).override == {"fiscal": 1}
    with pytest.raises(HTTPException) as e:
        _go(sim_api.faculty_override(sim_api.OverrideBody(user_id="stu1", run_id=rid, day=3, scores={"fiscal": 1})))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        _go(sim_api.faculty_override(sim_api.OverrideBody(user_id="stu1", run_id=rid, day=1, scores={"vibes": 2})))
    assert e.value.status_code == 400

    _go(sim_api.faculty_settings(sim_api.SettingsBody(scenario="running-dry", open_all=True)))
    assert state.open_all("running-dry")
