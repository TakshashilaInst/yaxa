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


# ---------------------------------------------------------------- Task 2: learners take the check
import asyncio  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from deeptutor.yaxa import schedule, store  # noqa: E402


def as_user(monkeypatch, uid: str, *, cohort: str | None = "GCPP45", staff: bool = False):
    if cohort and not schedule.load_cohort(cohort):
        schedule.save_cohort(schedule.Cohort(code=cohort, programme="GCPP"))
    user = store.load_user(uid, display_name=uid.title())
    user.enrolments = [store.Enrolment(programme="GCPP", track="DFA", cohort=cohort)] if cohort else [
        store.Enrolment(programme="GCPP", track="DFA")]
    store.save_user(user)
    monkeypatch.setattr(checks, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def _approved():
    s = _set(status="approved")
    checks.save_set(s)
    return s


def _answers(wrong: int = 0) -> dict[str, int]:
    """Right answer (index 0) for every question but the first `wrong`, which pick option 1."""
    return {f"q{i}": (1 if i <= wrong else 0) for i in range(1, 6)}


def _rows(cohort: str = "GCPP45"):
    return community.read_jsonl(community.root("checks", "attempts", cohort, "GCPP-PAC__CP11.jsonl"))


def test_learner_get_hides_answers(monkeypatch):
    as_user(monkeypatch, "asha")
    _approved()
    view = asyncio.run(checks.take("GCPP-PAC", "CP11"))
    assert view["available"] is True and len(view["questions"]) == 5
    dumped = json.dumps(view)
    assert '"correct"' not in dumped and '"why"' not in dumped and "misconception" not in dumped
    assert sorted(o["i"] for o in view["questions"][0]["options"]) == [0, 1, 2]


def test_draft_set_is_not_available(monkeypatch):
    as_user(monkeypatch, "asha")
    checks.save_set(_set())
    view = asyncio.run(checks.take("GCPP-PAC", "CP11"))
    assert view["available"] is False and view["questions"] == []


def test_submit_marks_and_explains(monkeypatch):
    as_user(monkeypatch, "asha")
    s = _approved()
    r = asyncio.run(checks.submit("GCPP-PAC", "CP11", checks.SubmitBody(version=s.version, answers=_answers(wrong=1))))
    assert r["score"] == 4 and r["ready"] is True
    q1 = r["results"][0]
    assert q1["right"] is False and q1["picked"] == 1 and q1["correct"] == 0
    assert q1["why_picked"] == "no" and q1["why_correct"] == "because" and q1["reading"] == "CP11 - State.pdf"


def test_first_flag_only_on_first_attempt(monkeypatch):
    as_user(monkeypatch, "asha")
    s = _approved()
    for wrong in (3, 0):
        asyncio.run(checks.submit("GCPP-PAC", "CP11", checks.SubmitBody(version=s.version, answers=_answers(wrong))))
    assert [r["first"] for r in _rows()] == [True, False]
    status = checks.learner_status("asha", "GCPP-PAC", "CP11")
    assert status == {"available": True, "best": 5, "ready": True, "attempts": 2}


def test_submit_against_old_version_is_409(monkeypatch):
    as_user(monkeypatch, "asha")
    s = _approved()
    with pytest.raises(HTTPException) as e:
        asyncio.run(checks.submit("GCPP-PAC", "CP11", checks.SubmitBody(version=s.version + 1, answers=_answers())))
    assert e.value.status_code == 409


def test_submit_missing_answer_is_400(monkeypatch):
    as_user(monkeypatch, "asha")
    s = _approved()
    a = _answers()
    a.pop("q5")
    with pytest.raises(HTTPException) as e:
        asyncio.run(checks.submit("GCPP-PAC", "CP11", checks.SubmitBody(version=s.version, answers=a)))
    assert e.value.status_code == 400


def test_learner_without_cohort_can_take_check(monkeypatch):
    as_user(monkeypatch, "ravi", cohort=None)
    s = _approved()
    asyncio.run(checks.submit("GCPP-PAC", "CP11", checks.SubmitBody(version=s.version, answers=_answers())))
    assert len(_rows("_none")) == 1


# ---------------------------------------------------------------- Task 3: drafting and the editor
def _q_json(n: int, correct: int = 0) -> dict:
    return {"text": f"Drafted {n}?", "uses": 1, "options": [
        {"text": f"opt{j}", "correct": j == correct, "why": f"why{j}", "misconception": "" if j == correct else f"Misc {n}.{j}"}
        for j in range(3)]}


class FakeModel:
    """Stands in for the shared model: returns queued replies, counts calls."""

    def __init__(self, *replies: str):
        self.replies, self.calls = list(replies), 0

    async def __call__(self, config, messages, max_tokens=0):
        self.calls += 1
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


@pytest.fixture
def model(monkeypatch):
    passages = [{"title": "State, a Political Institution", "file": "CP11 - State.pdf", "text": "The State is permanent.", "kb": "GCPP"}]

    async def fake_retrieve(kb, query, top_k, corpus=""):
        return passages

    monkeypatch.setattr(checks.grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(checks, "resolve_for", lambda uid: object())
    fake = FakeModel(json.dumps({"questions": [_q_json(n) for n in range(1, 6)]}))
    monkeypatch.setattr(checks, "complete_text", fake)
    return fake


def test_draft_saves_valid_draft(monkeypatch, model):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    s = asyncio.run(checks.admin_draft("GCPP-PAC", "CP11"))
    saved = checks.load_set("GCPP-PAC", "CP11")
    assert saved.status == "draft" and [q.id for q in saved.questions] == ["q1", "q2", "q3", "q4", "q5"]
    assert saved.questions[0].reading == "CP11 - State.pdf" and s["questions"][0]["options"][0]["correct"] is True


def test_draft_invalid_twice_is_502_and_saves_nothing(monkeypatch, model):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    model.replies = ["not json", '{"questions": []}']
    with pytest.raises(HTTPException) as e:
        asyncio.run(checks.admin_draft("GCPP-PAC", "CP11"))
    assert e.value.status_code == 502 and model.calls == 2 and checks.load_set("GCPP-PAC", "CP11") is None


def test_regenerate_replaces_only_that_question(monkeypatch, model):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    checks.save_set(_set())
    model.replies = [json.dumps({"questions": [_q_json(9)]})]
    asyncio.run(checks.admin_regenerate("GCPP-PAC", "CP11", "q3"))
    texts = [q.text for q in checks.load_set("GCPP-PAC", "CP11").questions]
    assert texts == ["Q1?", "Q2?", "Drafted 9?", "Q4?", "Q5?"]


def test_wording_edit_keeps_approved_and_answer_version(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    s = _set(status="approved")
    checks.save_set(s)
    s.questions[0].text = "Q1, reworded?"
    asyncio.run(checks.admin_save("GCPP-PAC", "CP11", checks.EditBody(questions=s.questions)))
    saved = checks.load_set("GCPP-PAC", "CP11")
    assert saved.status == "approved" and saved.version == 2 and saved.answer_version == 1


def test_changing_correct_answer_bumps_answer_version(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    s = _set(status="approved")
    checks.save_set(s)
    s.questions[0].options[0].correct, s.questions[0].options[1].correct = False, True
    s.questions[0].options[1].misconception, s.questions[0].options[0].misconception = "", "Now wrong"
    asyncio.run(checks.admin_save("GCPP-PAC", "CP11", checks.EditBody(questions=s.questions)))
    assert checks.load_set("GCPP-PAC", "CP11").answer_version == 2


def test_invalid_edit_is_400(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    s = _set()
    checks.save_set(s)
    with pytest.raises(HTTPException) as e:
        asyncio.run(checks.admin_save("GCPP-PAC", "CP11", checks.EditBody(questions=s.questions[:3])))
    assert e.value.status_code == 400


def test_approve_and_unpublish(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    checks.save_set(_set())
    asyncio.run(checks.admin_approve("GCPP-PAC", "CP11"))
    saved = checks.load_set("GCPP-PAC", "CP11")
    assert saved.status == "approved" and saved.approved_by == "Boss"
    asyncio.run(checks.admin_unpublish("GCPP-PAC", "CP11"))
    assert checks.load_set("GCPP-PAC", "CP11").status == "draft"


def test_admin_list_shows_every_session(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    checks.save_set(_set(status="approved"))
    rows = asyncio.run(checks.admin_list("GCPP-PAC"))
    cp11 = next(r for r in rows if r["session"] == "CP11")
    assert cp11["status"] == "approved" and cp11["attempts"] == 0
    assert all(r["status"] == "none" for r in rows if r["session"] != "CP11")


def test_learner_cannot_use_admin_routes(monkeypatch):
    as_user(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(checks.admin_get("GCPP-PAC", "CP11"))
    assert e.value.status_code == 403
