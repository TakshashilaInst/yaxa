"""Learn session: the tutor chat teaching a session's idea through its approved case."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import api, cases, catalog, prompting, store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield
    catalog.get_catalog(fresh=True)


def _case(**kw) -> cases.Case:
    base = dict(module="GCPP-PAC", session="CP11", status="approved", title="Delhi's free electricity",
                situation="Delhi gives 200 units free. " + "word " * 100, opening="What happens to demand?",
                grasp=["Price below cost raises demand", "Someone pays the gap"])
    base.update(kw)
    return cases.Case(**base)


def _system(case):
    cat = catalog.get_catalog()
    mod = cat.module("GCPP-PAC")
    return prompting.build_system(profile={}, learner_name="Ravi", module=mod, unit=mod.unit("CP11"),
                                  faculty=None, socratic=False, case=case)


def test_build_system_with_case_includes_situation_and_grasp():
    s = _system(_case())
    assert "Learn session" in s and "Delhi gives 200 units free" in s and "Someone pays the gap" in s
    assert prompting.SOCRATIC_RULES in s  # question-first even though socratic=False was passed


def test_learn_chat_without_case_has_no_case_block():
    assert "Learn session" not in _system(None)


def test_framing_defines_state_as_weberian():
    assert "Weber" in prompting.TAKSHASHILA_FRAMING


def test_start_learn_seeds_opening_turn():
    conv = store.Conversation(user_id="ravi", module="GCPP-PAC", unit="CP11")
    api._start_learn(conv, _case())
    assert conv.kind == "learn" and conv.turns[0].role == "assistant" and conv.turns[0].content == "What happens to demand?"


def test_start_learn_without_case_is_plain_learn():
    conv = store.Conversation(user_id="ravi", module="GCPP-PAC", unit="CP11")
    api._start_learn(conv, None)
    assert conv.kind == "learn" and conv.turns == []


def test_learn_case_only_when_approved():
    cases.save_case(_case(status="draft"))
    assert api._learn_case("GCPP-PAC", "CP11") is None
    cases.save_case(_case())
    assert api._learn_case("GCPP-PAC", "CP11").title == "Delhi's free electricity"


def test_record_learn_turn_keeps_tried_and_explained():
    api._record_learn("ravi", "GCPP-PAC", "CP11", "c1")
    assert cases.learn_status("ravi", "GCPP-PAC", "CP11")["status"] == "in_progress"
    cases.mark_learn("ravi", "GCPP-PAC", "CP11", status="explained")
    api._record_learn("ravi", "GCPP-PAC", "CP11", "c1")
    assert cases.learn_status("ravi", "GCPP-PAC", "CP11")["status"] == "explained"


def test_progress_survives_unpublish():
    cases.save_case(_case())
    api._record_learn("ravi", "GCPP-PAC", "CP11", "c9")
    c = cases.load_case("GCPP-PAC", "CP11")
    c.status = "draft"
    cases.save_case(c)
    st = cases.learn_status("ravi", "GCPP-PAC", "CP11")
    assert st["status"] == "in_progress" and st["conversation_id"] == "c9" and st["case"] is False
