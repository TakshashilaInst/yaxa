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
