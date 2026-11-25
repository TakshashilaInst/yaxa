"""Cohort life, step 2–4 shared helpers: who sees which cohort, locked files, rate limits, mail."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, community, mailer, schedule, store
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    schedule.save_cohort(Cohort(code="GCPP46", programme="GCPP"))
    yield
    catalog.get_catalog(fresh=True)


def as_user(monkeypatch, uid: str, *, cohort: str | None = None, track: str | None = None, staff: bool = False):
    user = store.load_user(uid, display_name=uid.title())
    user.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort=cohort)] if cohort else []
    store.save_user(user)
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def test_learner_sees_own_cohort_and_ignores_asked_one(monkeypatch):
    as_user(monkeypatch, "asha", cohort="GCPP45", track="DFA")
    v = community.viewer("GCPP46")
    assert v.cohort.code == "GCPP45" and v.track == "DFA" and not v.staff


def test_learner_without_cohort_gets_none(monkeypatch):
    as_user(monkeypatch, "ravi")
    v = community.viewer(None)
    assert v.cohort is None and v.track is None


def test_staff_picks_cohort_and_unknown_is_404(monkeypatch):
    as_user(monkeypatch, "boss", staff=True)
    assert community.viewer("GCPP46").cohort.code == "GCPP46"
    with pytest.raises(HTTPException) as e:
        community.viewer("NOPE")
    assert e.value.status_code == 404


def test_jsonl_append_is_safe_under_threads(tmp_path):
    p = tmp_path / "x" / "log.jsonl"
    threads = [threading.Thread(target=community.append_jsonl, args=(p, {"n": i})) for i in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r["n"] for r in community.read_jsonl(p)) == list(range(40))


def test_update_json_and_rewrite_jsonl(tmp_path):
    p = tmp_path / "a.json"
    community.update_json(p, lambda d: (d or []) + [1])
    community.update_json(p, lambda d: d + [2])
    assert json.loads(p.read_text()) == [1, 2]
    q = tmp_path / "b.jsonl"
    community.append_jsonl(q, {"id": "1", "text": "a"})
    community.rewrite_jsonl(q, lambda rows: [{**r, "text": "b"} for r in rows])
    assert community.read_jsonl(q) == [{"id": "1", "text": "b"}]
    assert community.read_jsonl(tmp_path / "missing.jsonl") == []


def test_rate_limit():
    assert all(community.rate_ok("u", "chat", 3) for _ in range(3))
    assert not community.rate_ok("u", "chat", 3)
    assert community.rate_ok("u", "question", 3)


def test_mailer_not_configured_then_configured(tmp_path, monkeypatch):
    assert not mailer.configured()
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "yaxa-mail.json").write_text(json.dumps(
        {"host": "smtp.example.org", "port": 587, "username": "u", "password": "p", "from": "Yaxa <office@example.org>"}))
    assert mailer.configured()
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["to_host"] = (host, port)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent["tls"] = True
        def login(self, u, p):
            sent["login"] = u
        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.send("gcpp45@example.org", "Hello", "Body text")
    assert sent["to_host"] == ("smtp.example.org", 587) and sent["tls"] and sent["login"] == "u"
    assert sent["msg"]["To"] == "gcpp45@example.org" and sent["msg"]["Subject"] == "Hello"
