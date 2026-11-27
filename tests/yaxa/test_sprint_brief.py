"""Friday brief additions: explain-back share and gaps, anonymised brief-layer patterns, a debate framing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.yaxa import brief, cases, catalog, community, layers, schedule, sprint_brief, store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    monkeypatch.setattr(sprint_brief, "_staff_ids", lambda: {"boss"})
    yield
    catalog.get_catalog(fresh=True)


NOW = datetime(2026, 11, 27, 10, 0, tzinfo=schedule.IST)


def setup_cohort(n: int = 4):
    soon = (NOW + timedelta(days=1)).date().isoformat()
    schedule.save_cohort(schedule.Cohort(code="GCPP45", programme="GCPP",
                                         sessions=[schedule.Session(code="CP11", date=soon, time="10:00")]))
    cases.save_case(cases.Case(module="GCPP-Fundamentals", session="CP11", status="approved", title="Manipur", situation="x " * 160,
                               opening="What broke?", grasp=["State holds legitimate force", "Government is temporary"]))
    layers.save_layer(layers.Layer(module="GCPP-Fundamentals", session="CP11", status="approved",
                                   prompt="Which institutions hold authority over your problem?", self_check=["a", "b", "c"]))
    ids = []
    for i in range(n):
        uid = f"s{i}"
        u = store.load_user(uid, display_name=f"Student {i}")
        u.enrolments = [store.Enrolment(programme="GCPP", track="TP", cohort="GCPP45")]
        store.save_user(u)
        ids.append(uid)
    return ids


def write_layer(uid: str, text: str, title: str = "Drone rules"):
    data = brief.load(uid)
    data["problem"]["title"] = title
    data["layers"]["GCPP-Fundamentals/CP11"] = {"text": text}
    brief._save(uid, data)


class FakeModel:
    def __init__(self, reply: dict):
        self.reply, self.calls, self.messages = json.dumps(reply), 0, None

    async def __call__(self, config, messages, max_tokens=0):
        self.calls += 1
        self.messages = messages
        return self.reply


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(sprint_brief, "resolve_for", lambda uid: object())
    fake = FakeModel({"gaps": ["Mixing up State and government"], "weaknesses": ["Most named a ministry, not where its legitimacy comes from"],
                      "debate": "Is a State that loses its monopoly on force still a State?"})
    monkeypatch.setattr(sprint_brief, "complete_text", fake)
    return fake


def test_counts_explained_share(monkeypatch, model):
    ids = setup_cohort()
    cases.mark_learn(ids[0], "GCPP-Fundamentals", "CP11", status="explained", attempts=[{"missing": []}])
    cases.mark_learn(ids[1], "GCPP-Fundamentals", "CP11", status="tried", attempts=[{"missing": ["Government is temporary"]}])
    rows = sprint_brief.sprint_data("GCPP45", now=NOW)
    r = rows[0]
    assert (r["session"], r["enrolled"], r["learn"]["started"], r["learn"]["explained"]) == ("CP11", 4, 2, 1)
    assert r["layer"] == {"available": True, "written": 0}


def test_staff_excluded(monkeypatch, model):
    ids = setup_cohort()
    boss = store.load_user("boss", display_name="Boss")
    boss.enrolments = [store.Enrolment(programme="GCPP", track="TP", cohort="GCPP45")]
    store.save_user(boss)
    cases.mark_learn("boss", "GCPP-Fundamentals", "CP11", status="explained")
    r = sprint_brief.sprint_data("GCPP45", now=NOW)[0]
    assert r["enrolled"] == 4 and r["learn"]["explained"] == 0


def test_patterns_need_three_writers(monkeypatch, model):
    ids = setup_cohort()
    for uid in ids[:2]:
        write_layer(uid, "The ministry decides everything about drones in farming areas.")
    out = asyncio.run(sprint_brief.patterns(SimpleNamespace(id="boss"), "GCPP45", sprint_brief.sprint_data("GCPP45", now=NOW)[0], True))
    assert "ministry decides" not in json.dumps(model.messages or "")
    assert out["weaknesses"] == [] and out["note"]


def test_patterns_drop_quotations_and_problem_titles(monkeypatch, model):
    ids = setup_cohort()
    for uid in ids[:3]:
        write_layer(uid, "The ministry decides everything about drones in farming areas.", title="Kisan drone subsidy")
    model.reply = json.dumps({"gaps": ["Mixing up State and government"],
                              "weaknesses": ["One wrote that the ministry decides everything about drones", "Kisan drone subsidy is weak",
                                             "Most named an institution but not its legitimacy"],
                              "debate": "Is force enough?"})
    sess = sprint_brief.sprint_data("GCPP45", now=NOW)[0]
    out = asyncio.run(sprint_brief.patterns(SimpleNamespace(id="boss"), "GCPP45", sess, True))
    assert out["weaknesses"] == ["Most named an institution but not its legitimacy"]
    assert out["debate"] == "Is force enough?"
    assert "Student 0" not in model.messages[1]["content"] and "s0" not in model.messages[1]["content"].split()


def test_patterns_cached_until_data_changes(monkeypatch, model):
    ids = setup_cohort()
    for uid in ids[:3]:
        write_layer(uid, "Some reasoning here about who holds authority.")
    sess = sprint_brief.sprint_data("GCPP45", now=NOW)[0]
    asyncio.run(sprint_brief.patterns(SimpleNamespace(id="boss"), "GCPP45", sess, False))
    asyncio.run(sprint_brief.patterns(SimpleNamespace(id="boss"), "GCPP45", sess, False))
    assert model.calls == 1
    write_layer(ids[3], "A fourth student's reasoning about authority.")
    asyncio.run(sprint_brief.patterns(SimpleNamespace(id="boss"), "GCPP45", sprint_brief.sprint_data("GCPP45", now=NOW)[0], False))
    assert model.calls == 2


def test_endpoint_is_staff_only(monkeypatch, model):
    setup_cohort()
    u = store.load_user("s0")
    monkeypatch.setattr(sprint_brief, "_me", lambda: (SimpleNamespace(id="s0", is_admin=False), u))
    with pytest.raises(HTTPException) as e:
        asyncio.run(sprint_brief.sprint("GCPP45"))
    assert e.value.status_code == 403
