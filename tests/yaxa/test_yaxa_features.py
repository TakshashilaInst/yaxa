"""Yaxa Learn features: practice mode, the faculty cohort brief and the faculty panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, cohort, panel, practice, store
from deeptutor.yaxa.access import parse_json_reply


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield
    catalog.get_catalog(fresh=True)


# --------------------------------------------------------- model replies
def test_json_reply_is_found_inside_prose_and_fences() -> None:
    reply = 'Sure. ```json\n{"score": 2, "feedback": "Good {start}, see [1]."}\n``` Hope that helps.'
    assert parse_json_reply(reply) == {"score": 2, "feedback": "Good {start}, see [1]."}


def test_json_reply_skips_broken_objects_and_rejects_non_objects() -> None:
    assert parse_json_reply('{"oops": } then {"question": "Why?"}') == {"question": "Why?"}
    assert parse_json_reply("no json here") is None
    assert parse_json_reply("[1, 2]") is None


# ---------------------------------------------------------------- practice
def test_unit_status_needs_two_full_marks_in_a_row() -> None:
    assert practice.unit_status([]) == "new"
    assert practice.unit_status([3]) == "practising"
    assert practice.unit_status([3, 2]) == "practising"
    assert practice.unit_status([1, 3, 3]) == "mastered"


def test_progress_and_next_unit_follow_the_student_scores() -> None:
    mod = catalog.get_catalog().module("GCPP-ER1")
    first, second = mod.units[0].id, mod.units[1].id
    for score in (3, 3):
        store.save_practice(store.PracticeItem(user_id="u_p", module=mod.code, unit=first, question="q", score=score))
    store.save_practice(store.PracticeItem(user_id="u_p", module=mod.code, unit=second, question="q"))  # unanswered
    rows = {r["id"]: r for r in practice._progress("u_p", mod)}
    assert rows[first]["status"] == "mastered" and rows[first]["answered"] == 2
    assert rows[second]["status"] == "new"
    assert practice._pick_unit(mod, list(rows.values()), None).id == second


def test_practice_items_are_per_user() -> None:
    store.save_practice(store.PracticeItem(user_id="u_a", module="GCPP-ER1", question="a"))
    store.save_practice(store.PracticeItem(user_id="u_b", module="GCPP-Fundamentals", question="b"))
    assert [i.question for i in store.list_practice("u_a")] == ["a"]
    assert len(store.list_practice()) == 2
    assert [i.question for i in store.list_practice(module="GCPP-Fundamentals")] == ["b"]


# ------------------------------------------------------------ cohort brief
def test_anonymise_removes_names_and_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    user = store.load_user("u_n", display_name="Karthik Raman")
    store.save_user(user)
    monkeypatch.setattr("deeptutor.multi_user.identity.load_users", lambda: {"shruti.k@example.org": {"id": "u_s"}})
    scrub = cohort._name_scrubber()
    text = "I'm Karthik; Shruti and karthik asked shruti.k@example.org about rent control."
    out = cohort.anonymise(text, scrub)
    assert "Karthik" not in out and "karthik" not in out and "Shruti" not in out and "@" not in out
    assert "rent control" in out


def test_collect_counts_students_only_and_flags_unsupported_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cohort, "_staff_ids", lambda: {"u_admin"})
    monkeypatch.setattr(cohort, "_name_scrubber", lambda: None)
    for uid, cited in (("u_1", True), ("u_2", False), ("u_admin", False)):
        conv = store.Conversation(user_id=uid, module="GCPP-ER1", unit="CP21", title="t")
        conv.turns.append(store.Turn(role="user", content=f"question from {uid}"))
        conv.turns.append(store.Turn(role="assistant", content="answer", citations=[{"n": 1, "dangling": False}] if cited else []))
        store.save_conversation(conv)
    data = cohort.collect("GCPP-ER1", 7)
    assert data["stats"]["students"] == 2 and data["stats"]["questions"] == 2
    assert data["stats"]["unsupported"] == 1
    assert data["gaps"] == ["question from u_2"]
    assert next(u for u in data["units"] if u["id"] == "CP21")["questions"] == 2


# -------------------------------------------------------------------- panel
def test_panellists_may_cite_module_passages_and_only_their_own_writing() -> None:
    mod = [{"kb": "M"}, {"kb": "M"}]
    own = {"nitin": [{"kb": "N"}], "pranay": [{"kb": "P"}, {"kb": "P"}]}
    numbered, allowed = panel.allocate(mod, own)
    assert len(numbered) == 5
    assert allowed["nitin"] == [1, 2, 3]
    assert allowed["pranay"] == [1, 2, 4, 5]
    assert numbered[3]["kb"] == "P"


def test_saved_panel_keeps_its_kind_and_phases() -> None:
    conv = store.Conversation(user_id="u_x", kind="panel", title="Should India cap rents?")
    conv.turns.append(store.Turn(role="assistant", content="...", faculty="nitin-pai", phase="opening"))
    store.save_conversation(conv)
    assert store.list_conversations("u_x")[0]["kind"] == "panel"
    assert store.load_conversation("u_x", conv.id).turns[0].phase == "opening"


def test_json_reply_tolerates_raw_newlines_in_strings() -> None:
    assert parse_json_reply('{"question": "Line one.\nLine two?"}') == {"question": "Line one.\nLine two?"}
