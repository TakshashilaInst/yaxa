"""Session check: a faculty-approved 5-question check before each webinar, and the brief it feeds."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, checks, community


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    yield
    catalog.get_catalog(fresh=True)


def _set(**kw) -> checks.CheckSet:
    """A valid 5-question set: option 0 right, options 1-2 wrong with named misconceptions."""
    qs = [
        checks.Question(
            id=f"q{i}",
            text=f"Q{i}?",
            reading="CP11 - State.pdf",
            options=[
                checks.Option(text="right", correct=True, why="because"),
                checks.Option(text="wrong a", why="no", misconception="Mixes up A"),
                checks.Option(text="wrong b", why="no", misconception="Mixes up B"),
            ],
        )
        for i in range(1, 6)
    ]
    return checks.CheckSet(module="GCPP-PAC", session="CP11", questions=qs, **kw)


# ---------------------------------------------------------------- Task 1: model and storage
def test_valid_set_has_no_problems():
    assert checks.validate(_set()) == []


def test_rejects_wrong_question_count():
    s = _set()
    s.questions = s.questions[:4]
    assert any("5 questions" in p for p in checks.validate(s))


def test_rejects_two_correct_options():
    s = _set()
    s.questions[0].options[1].correct = True
    assert checks.validate(s)


def test_rejects_wrong_option_without_misconception():
    s = _set()
    s.questions[2].options[1].misconception = ""
    assert checks.validate(s)


def test_rejects_five_options():
    s = _set()
    s.questions[0].options += [checks.Option(text="x", why="y", misconception="z")] * 2
    assert checks.validate(s)


def test_save_and_load_roundtrip():
    checks.save_set(_set())
    assert checks.load_set("GCPP-PAC", "CP11").questions[0].text == "Q1?"


def test_load_missing_is_none():
    assert checks.load_set("GCPP-PAC", "CP99") is None
