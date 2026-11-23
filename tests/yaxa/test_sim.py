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
