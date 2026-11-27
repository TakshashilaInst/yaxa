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
    base = dict(module="GCPP-Fundamentals", session="CP11", title="Delhi's free electricity", situation=words(160),
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
    assert cases.load_case("GCPP-Fundamentals", "CP11") == _case()
    assert cases.load_case("GCPP-Fundamentals", "CP12") is None


def test_public_view_hides_grasp():
    v = cases.public_view(_case(status="approved"))
    assert "grasp" not in v and v["title"] == "Delhi's free electricity" and v["opening"]


# ---------------------------------------------------------------- Task 2: faculty draft, edit, approve
import asyncio  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from deeptutor.yaxa import schedule, store  # noqa: E402


def as_user(monkeypatch, uid: str, *, cohort: str | None = "GCPP45", staff: bool = False):
    if cohort and not schedule.load_cohort(cohort):
        schedule.save_cohort(schedule.Cohort(code=cohort, programme="GCPP"))
    user = store.load_user(uid, display_name=uid.title())
    user.enrolments = [store.Enrolment(programme="GCPP", track="TP", cohort=cohort)] if cohort else [
        store.Enrolment(programme="GCPP", track="TP")]
    store.save_user(user)
    monkeypatch.setattr(cases, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


class FakeModel:
    def __init__(self, *replies: str):
        self.replies, self.calls = list(replies), 0

    async def __call__(self, config, messages, max_tokens=0):
        self.calls += 1
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


DRAFT = json.dumps({"title": "Delhi's free electricity", "situation": words(170), "opening": "What happens to demand?",
                    "grasp": ["Price below cost raises demand", "Someone pays the gap"]})


@pytest.fixture
def model(monkeypatch):
    passages = [{"title": "State, a Political Institution", "file": "CP11 - State.pdf", "text": "The State is permanent.", "kb": "GCPP"}]

    async def fake_retrieve(kb, query, top_k, corpus=""):
        return passages

    monkeypatch.setattr(cases.grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(cases, "resolve_for", lambda uid: object())
    fake = FakeModel(DRAFT)
    monkeypatch.setattr(cases, "complete_text", fake)
    return fake


def test_draft_saves_valid_draft(monkeypatch, model):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    out = asyncio.run(cases.admin_draft("GCPP-Fundamentals", "CP11"))
    saved = cases.load_case("GCPP-Fundamentals", "CP11")
    assert saved.status == "draft" and saved.title == "Delhi's free electricity" and len(saved.grasp) == 2
    assert out["grasp"] == saved.grasp  # staff see the grasp notes


def test_draft_prompt_defines_state_as_weberian(monkeypatch, model):
    assert "Weber" in cases.DRAFT_PROMPT


def test_bad_draft_twice_is_502_and_nothing_saved(monkeypatch, model):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    model.replies = ["not json"]
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.admin_draft("GCPP-Fundamentals", "CP11"))
    assert e.value.status_code == 502 and model.calls == 2 and cases.load_case("GCPP-Fundamentals", "CP11") is None


def _body(**kw):
    c = _case(**kw)
    return cases.EditBody(title=c.title, situation=c.situation, opening=c.opening, grasp=c.grasp)


def test_edit_invalid_is_400_with_problems(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    cases.save_case(_case())
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.admin_save("GCPP-Fundamentals", "CP11", _body(opening="")))
    assert e.value.status_code == 400 and e.value.detail["problems"]


def test_edit_keeps_approval_and_bumps_version(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    cases.save_case(_case(status="approved", version=3))
    asyncio.run(cases.admin_save("GCPP-Fundamentals", "CP11", _body(title="Delhi's subsidy, revisited")))
    c = cases.load_case("GCPP-Fundamentals", "CP11")
    assert c.status == "approved" and c.version == 4 and c.title == "Delhi's subsidy, revisited"


def test_approve_and_unpublish(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    cases.save_case(_case())
    out = asyncio.run(cases.admin_approve("GCPP-Fundamentals", "CP11"))
    assert out["status"] == "approved" and out["approved_by"] == "Boss" and out["approved_at"]
    assert asyncio.run(cases.admin_unpublish("GCPP-Fundamentals", "CP11"))["status"] == "draft"


def test_approve_invalid_is_400(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    cases.save_case(_case(grasp=["only one"]))
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.admin_approve("GCPP-Fundamentals", "CP11"))
    assert e.value.status_code == 400


def test_admin_list_covers_every_unit(monkeypatch):
    as_user(monkeypatch, "boss", cohort=None, staff=True)
    cases.save_case(_case(status="approved"))
    rows = asyncio.run(cases.admin_list("GCPP-Fundamentals"))
    assert len(rows) == len(catalog.get_catalog().module("GCPP-Fundamentals").units)
    assert next(r for r in rows if r["session"] == "CP11")["status"] == "approved"
    assert next(r for r in rows if r["session"] == "CP12")["status"] == "none"


def test_learner_cannot_draft(monkeypatch, model):
    as_user(monkeypatch, "ravi")
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.admin_draft("GCPP-Fundamentals", "CP11"))
    assert e.value.status_code == 403 and model.calls == 0


# ---------------------------------------------------------------- Task 3: learner view, progress, explain-back
def test_learner_sees_approved_case_without_grasp(monkeypatch):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    v = asyncio.run(cases.learner_get("GCPP-Fundamentals", "CP11"))
    assert v["title"] == "Delhi's free electricity" and "grasp" not in v
    assert "legitimate force" not in json.dumps(v)


def test_learn_without_case_is_404(monkeypatch):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case())  # a draft is not visible
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.learner_get("GCPP-Fundamentals", "CP11"))
    assert e.value.status_code == 404


@pytest.fixture
def judge(monkeypatch):
    monkeypatch.setattr(cases, "resolve_for", lambda uid: object())
    fake = FakeModel(json.dumps({"got": ["The State holds legitimate force"], "missing": [], "feedback": "Clear."}))
    monkeypatch.setattr(cases, "complete_text", fake)
    return fake


EXPLAIN = cases.ExplainBody(text=words(30))


def test_explain_too_short_is_400(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", cases.ExplainBody(text="the state is big")))
    assert e.value.status_code == 400 and "own words" in e.value.detail and judge.calls == 0


def test_explain_records_explained_when_nothing_missing(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    out = asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", EXPLAIN))
    assert out == {"got": ["The State holds legitimate force"], "missing": [], "next": [], "feedback": "Clear."}
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11")["status"] == "explained"


def test_explain_records_tried_when_something_missing(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    judge.replies = [json.dumps({"got": [], "missing": ["Government is its agent"], "feedback": "Close."})]
    asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", EXPLAIN))
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11")["status"] == "tried"


def test_explain_bad_reply_is_502(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    judge.replies = ["nope"]
    with pytest.raises(HTTPException) as e:
        asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", EXPLAIN))
    assert e.value.status_code == 502 and judge.calls == 2
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11")["status"] == "not_started"


def test_explain_text_stays_in_own_file(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    secret = "zebracrossing " * 30
    asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", cases.ExplainBody(text=secret)))
    for f in community.root("cases").rglob("*"):
        if f.is_file():
            assert "zebracrossing" not in f.read_text()
    assert "zebracrossing" in json.dumps(cases.learn_progress("ravi"))


def test_learn_status_defaults(monkeypatch):
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11") == {"case": False, "status": "not_started", "conversation_id": None}
    cases.save_case(_case(status="approved"))
    cases.mark_learn("ravi", "GCPP-Fundamentals", "CP11", status="in_progress", conversation_id="c1")
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11") == {"case": True, "status": "in_progress", "conversation_id": "c1"}


# ---------------------------------------------------------------- explain-back judges the core idea
def test_explain_prompt_judges_core_idea_not_case_application():
    p = cases.EXPLAIN_PROMPT
    assert "core idea" in p and '"next"' in p


def test_explain_returns_next_prompts_and_case_points_do_not_block(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    judge.replies = [json.dumps({"got": ["State vs government"], "missing": [],
                                 "next": ["What did President's Rule change on the ground?"], "feedback": "Right."})]
    out = asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", EXPLAIN))
    assert out["next"] == ["What did President's Rule change on the ground?"]
    assert cases.learn_status("ravi", "GCPP-Fundamentals", "CP11")["status"] == "explained"


def test_explain_without_next_defaults_to_empty(monkeypatch, judge):
    as_user(monkeypatch, "ravi")
    cases.save_case(_case(status="approved"))
    assert asyncio.run(cases.explain("GCPP-Fundamentals", "CP11", EXPLAIN))["next"] == []
