"""Libraries page API: status, sync requests and the name review queue (staff only)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.yaxa import catalog, library_api, store
from deeptutor.yaxa.library import sync
from deeptutor.yaxa.library.ledger import Entry, Ledger

MD = "# Webinar transcript: X\n- note\n\n[00:00:00] Kajari Kamal: As Deepak said, and Deepak Lal wrote.\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    audit: list = []
    monkeypatch.setattr(library_api, "log_admin_action", lambda *a, **k: audit.append((a, k)))
    monkeypatch.setattr(library_api, "_public_full", lambda: {"Deepak Lal"})
    return SimpleNamespace(path=tmp_path, audit=audit)


def as_user(monkeypatch, *, admin=False, role="student") -> None:
    cu = SimpleNamespace(id="u1", is_admin=admin, username="someone")
    monkeypatch.setattr(library_api, "_me", lambda: (cu, store.YaxaUser(user_id="u1", role=role)))


def seed_ledger() -> None:
    led = Ledger(sync.library_root() / "ledger.json")
    led.entries = {
        "a": Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="A.pdf", status="live", path="GCPP/x/A.pdf"),
        "p": Entry(drive_id="p", kb="", kind="", indexed_as="", status="skipped", error="unsupported type .pptx", path="GCPP/x/s.pptx"),
        "r": Entry(drive_id="r", kb="DFA", kind="recording", indexed_as="Webinar - X.md", status="review", path="GCPP/x/X.mp4",
                   placement={"title": "Webinar: X"}, flags=[{"name": "Deepak", "context": "As Deepak said", "at": "00:00:00"}]),
    }
    led.save()
    private = sync.library_root() / "private" / "r"
    private.mkdir(parents=True)
    (private / "redacted.md").write_text(MD)


def run(coro):
    return asyncio.run(coro)


def test_students_are_refused(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch)
    for call in (library_api.status(), library_api.request_sync(), library_api.review_queue()):
        with pytest.raises(HTTPException) as exc:
            run(call)
        assert exc.value.status_code == 403


def test_status_counts_and_problems(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, role="faculty")
    seed_ledger()
    data = run(library_api.status())
    assert {"kb": "DFA", "counts": {"live": 1, "review": 1}} in data["libraries"]
    assert data["problems"] == [{"drive_id": "p", "path": "GCPP/x/s.pptx", "status": "skipped", "error": "unsupported type .pptx"}]
    assert data["running"] is False and data["needs_review"] == 1


def test_sync_request_writes_flag(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    assert run(library_api.request_sync()) == {"queued": True}
    assert (sync.library_root() / "request").exists()


def test_review_queue_lists_flags(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    seed_ledger()
    items = run(library_api.review_queue())
    assert items == [{"drive_id": "r", "path": "GCPP/x/X.mp4", "title": "Webinar: X",
                      "flags": [{"name": "Deepak", "context": "As Deepak said", "at": "00:00:00"}]}]


def test_decide_remove_approves_and_queues(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    seed_ledger()
    out = run(library_api.decide("r", library_api.Decision(decisions={"Deepak": "remove"})))
    assert out == {"status": "approved"}
    text = (sync.library_root() / "private" / "r" / "redacted.md").read_text()
    assert "As a participant said" in text and "Deepak Lal" in text
    entry = Ledger(sync.library_root() / "ledger.json").load().entries["r"]
    assert entry.status == "approved" and entry.flags == []
    assert (sync.library_root() / "request").exists()
    assert "Deepak" not in repr(home.audit)  # names never reach the audit log


def test_decide_keep_remembers_the_name(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    seed_ledger()
    run(library_api.decide("r", library_api.Decision(decisions={"Deepak": "keep"})))
    entry = Ledger(sync.library_root() / "ledger.json").load().entries["r"]
    assert entry.allow == ["Deepak"] and "As Deepak said" in (sync.library_root() / "private" / "r" / "redacted.md").read_text()


def test_decide_needs_every_flag_answered(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    seed_ledger()
    with pytest.raises(HTTPException) as exc:
        run(library_api.decide("r", library_api.Decision(decisions={})))
    assert exc.value.status_code == 400


def test_reject_drops_the_recording(home: SimpleNamespace, monkeypatch) -> None:
    as_user(monkeypatch, admin=True)
    seed_ledger()
    run(library_api.decide("r", library_api.Decision(reject=True)))
    entry = Ledger(sync.library_root() / "ledger.json").load().entries["r"]
    assert entry.status == "rejected" and entry.error == "not used: a reviewer chose not to use this recording"
    assert not (sync.library_root() / "private" / "r").exists()
