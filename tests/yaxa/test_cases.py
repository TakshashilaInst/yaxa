"""Weekly case: a faculty-approved real Indian case per session, and the Learn session built on it."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, cases, community


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    yield
    catalog.get_catalog(fresh=True)


def words(n: int) -> str:
    return " ".join(["word"] * n)


def _case(**kw) -> cases.Case:
    base = dict(module="GCPP-PAC", session="CP11", title="Delhi's free electricity", situation=words(160),
                opening="Who should decide, and why?", grasp=["The State holds legitimate force", "Government is its agent"])
    base.update(kw)
    return cases.Case(**base)


# ---------------------------------------------------------------- Task 1: model and storage
def test_valid_case_has_no_problems():
    assert cases.validate(_case()) == []


def test_rejects_short_situation():
    problems = cases.validate(_case(situation=words(cases.MIN_WORDS - 1)))
    assert any("situation" in p.lower() for p in problems)


def test_rejects_missing_opening():
    assert cases.validate(_case(opening="  "))


def test_rejects_grasp_count():
    assert cases.validate(_case(grasp=["one"]))
    assert cases.validate(_case(grasp=[f"g{i}" for i in range(6)]))


def test_roundtrip():
    cases.save_case(_case())
    assert cases.load_case("GCPP-PAC", "CP11") == _case()
    assert cases.load_case("GCPP-PAC", "CP12") is None


def test_public_view_hides_grasp():
    v = cases.public_view(_case(status="approved"))
    assert "grasp" not in v and v["title"] == "Delhi's free electricity" and v["opening"]
