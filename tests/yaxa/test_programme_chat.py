"""'Ask across my programme': one chat grounded in every library a student can use."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.yaxa import access, catalog, grounding, prompting, store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)


def _student(programme: str, track: str | None) -> tuple[SimpleNamespace, store.YaxaUser]:
    user = store.load_user("s1", display_name="Student")
    user.enrolments = [store.Enrolment(programme=programme, track=track)]
    return SimpleNamespace(id="s1", is_admin=False), user


def test_programme_kbs_cover_enrolled_modules_once_plus_faculty() -> None:
    cat = catalog.get_catalog()
    cu, user = _student("GCPP", "TP")
    kbs = access.programme_kbs(cat, cu, user)
    module_kbs = [cat.modules[c].kb for c in access._allowed_modules(cat, cu, user)
                  if cat.modules[c].available and cat.modules[c].kb]
    faculty_kbs = [f.kb for f in cat.faculty.values() if f.kb]
    assert len(kbs) == len(set(kbs)), "each library searched once"
    assert set(kbs) == set(module_kbs) | set(faculty_kbs)
    # course libraries come before faculty writing
    assert kbs.index(module_kbs[0]) < min(kbs.index(k) for k in faculty_kbs)


def test_programme_kbs_exclude_other_tracks() -> None:
    cat = catalog.get_catalog()
    cu, user = _student("GCPP", "TP")
    kbs = access.programme_kbs(cat, cu, user)
    dfa_only = {cat.modules[c].kb for c in cat.modules if c.startswith("DFA-") and cat.modules[c].kb}
    assert dfa_only and not (dfa_only & set(kbs))


def test_retrieve_across_merges_by_score_and_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    async def fake(kb: str, query: str, top_k: int, *, corpus: str = "") -> list[dict]:
        calls.append((kb, top_k))
        base = {"A": 0.9, "B": 0.5, "C": 0.7}[kb]
        return [{"kb": kb, "file": f"{kb}{i}.pdf", "score": base - i / 100} for i in range(top_k)]

    monkeypatch.setattr(grounding, "retrieve", fake)
    out = asyncio.run(grounding.retrieve_across(["A", "B", "C"], "q", 5))
    assert len(out) == 5
    assert [p["kb"] for p in out[:3]] == ["A", "A", "A"]  # best scores first
    assert all(out[i]["score"] >= out[i + 1]["score"] for i in range(4))
    assert {kb for kb, _ in calls} == {"A", "B", "C"}


def test_retrieve_across_survives_a_failed_library_and_blank_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(kb: str, query: str, top_k: int, *, corpus: str = "") -> list[dict]:
        if kb == "BAD":
            raise RuntimeError("index missing")
        return [{"kb": kb, "file": "x.pdf", "score": ""}] if kb == "BLANK" else [{"kb": kb, "file": "y.pdf", "score": 0.4}]

    monkeypatch.setattr(grounding, "retrieve", fake)
    out = asyncio.run(grounding.retrieve_across(["BAD", "BLANK", "OK"], "q", 4))
    assert [p["kb"] for p in out] == ["OK", "BLANK"]


def test_programme_prompt_names_the_modules_and_asks_for_connections() -> None:
    cat = catalog.get_catalog()
    cu, user = _student("GCPP", "TP")
    mods = [cat.modules[c] for c in access._allowed_modules(cat, cu, user)]
    system = prompting.build_system(profile={}, learner_name="S", module=None, unit=None,
                                    faculty=None, socratic=False, programme_modules=mods)
    assert "across" in system.lower()
    for m in mods[:3]:
        assert m.title in system
