"""A session tag set by hand (CS22) survives a sync that only knows the course (CS2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa.library import labels


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))


def test_a_more_specific_session_tag_survives_a_course_level_relabel():
    labels.upsert("DFA", "a.pdf", {"title": "t", "unit": "CS2"})
    data = labels._load("DFA")
    data["files"]["a.pdf"]["unit"] = "CS22"
    labels._store("DFA", data)
    labels.upsert("DFA", "a.pdf", {"title": "t", "unit": "CS2"}, keep_curated=True)
    assert labels._load("DFA")["files"]["a.pdf"]["unit"] == "CS22"


def test_a_different_code_still_replaces_the_tag():
    labels.upsert("DFA", "a.pdf", {"title": "t", "unit": "CS22"})
    labels.upsert("DFA", "a.pdf", {"title": "t", "unit": "CS3"}, keep_curated=True)
    assert labels._load("DFA")["files"]["a.pdf"]["unit"] == "CS3"
