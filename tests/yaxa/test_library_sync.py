"""One library sync run end to end, with fake Drive, Sarvam and indexer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deeptutor.yaxa import catalog
from deeptutor.yaxa.library import sync
from deeptutor.yaxa.library.drive import DriveFile
from deeptutor.yaxa.library.ledger import Ledger

AS = ("GCPP", "DFA Defence and Foreign Affairs", "DFA-AS Introduction to Arthashastra")
REC_DIR = AS + ("Recordings", "DFA26 Jun 2026")
PUBLIC = {"full": ["Deepak Lal"], "single": [], "other": []}


class Fake:
    def __init__(self, files: list[DriveFile], said: str = "Thanks everyone. Ravi asked about saptanga.") -> None:
        self.files, self.said = files, said
        self.kb_add_calls: list[tuple[str, list[str]]] = []
        self.transcribed: list[str] = []
        self.fail_kb_add = 0

    def deps(self) -> sync.Deps:
        return sync.Deps(walk=lambda: list(self.files), download=self.download, transcribe=self.transcribe,
                         kb_add=self.kb_add, students=lambda: {"Ravi", "Deepak"}, public=lambda: PUBLIC, api_key="k")

    def download(self, file_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nravi.k: hello\n" if dest.suffix == ".vtt" else f"content {file_id}")
        return dest

    def transcribe(self, media, vtt, keyterms, api_key, work):
        self.transcribed.append(media.name)
        assert "Kajari Kamal" in keyterms and "Introduction to Arthashastra" in keyterms
        return [{"start": 0.0, "end": 30.0, "text": self.said, "speaker": "Kajari Kamal"},
                {"start": 31.0, "end": 35.0, "text": "Is it still relevant?", "speaker": "ravi.k"}], "sarvam+zoom"

    def kb_add(self, kb: str, docs: Path) -> None:
        if self.fail_kb_add:
            self.fail_kb_add -= 1
            raise RuntimeError("indexer crashed")
        self.kb_add_calls.append((kb, sorted(p.name for p in docs.iterdir())))


def pdf(id_, name, path=AS + ("Readings",), md5="m1"):
    return DriveFile(id=id_, name=name, path=path, mime="application/pdf", md5=md5)


def mp4(id_="r1", name="CS22 - Concept Cluster I - Kajari Kamal.mp4"):
    return DriveFile(id=id_, name=name, path=REC_DIR, mime="video/mp4", md5="mv")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield tmp_path
    catalog.get_catalog(fresh=True)


def labels(kb: str) -> dict:
    return yaml.safe_load(catalog.sources_path(kb).read_text())["files"]


def ledger() -> Ledger:
    return Ledger(sync.library_root() / "ledger.json").load()


def test_reading_and_recording_go_live(home: Path) -> None:
    fake = Fake([pdf("a", "CS22 - Kautilya.pdf"), mp4()])
    summary = sync.run(fake.deps())
    assert summary["added"] == 2 and summary["failed"] == 0
    assert fake.kb_add_calls == [("DFA", ["CS22 - Kautilya.pdf", "Webinar - CS22 - Concept Cluster I - Kajari Kamal.md"])]
    files = labels("DFA")
    assert files["CS22 - Kautilya.pdf"]["drive_id"] == "a" and files["CS22 - Kautilya.pdf"]["module"] == "DFA-AS"
    rec = files["Webinar - CS22 - Concept Cluster I - Kajari Kamal.md"]
    assert (rec["kind"], rec["corpus"]) == ("video", "Webinar recording, DFA26 (Jun 2026)")
    assert {e.status for e in ledger().entries.values()} == {"live"}
    assert not any((sync.library_root() / "private").rglob("*.mp4"))  # raw media gone
    assert not any((sync.library_root() / "staging").rglob("*.*"))
    learned = (sync.library_root() / "private" / "learned-names.txt").read_text()
    assert "ravi" in learned.lower()


def test_flagged_recording_waits_for_review(home: Path) -> None:
    fake = Fake([mp4()], said="As Deepak Lal argues, and as Deepak said earlier in class.")
    summary = sync.run(fake.deps())
    entry = ledger().entries["r1"]
    assert summary["review"] == 1 and entry.status == "review" and entry.flags[0]["name"] == "Deepak"
    assert fake.kb_add_calls == []
    assert (sync.library_root() / "private" / "r1" / "redacted.md").is_file()


def test_second_run_is_a_no_op(home: Path) -> None:  # [RF1]
    fake = Fake([pdf("a", "CS22 - Kautilya.pdf"), mp4()])
    sync.run(fake.deps())
    fake.kb_add_calls.clear()
    summary = sync.run(fake.deps())
    assert summary["added"] == 0 and fake.kb_add_calls == [] and fake.transcribed == ["media.mp4"]


def test_rename_relabels_without_reindexing(home: Path) -> None:  # [RF1]
    fake = Fake([pdf("a", "CS22 - Kautilya.pdf")])
    sync.run(fake.deps())
    fake.files = [pdf("a", "CS22 - Kautilya and the Mandala.pdf",
                      path=("GCPP", "DFA Defence and Foreign Affairs", "DFA-SE Strategic Economics", "Readings"))]
    fake.kb_add_calls.clear()
    summary = sync.run(fake.deps())
    assert summary["relabelled"] == 1 and fake.kb_add_calls == []
    label = labels("DFA")["CS22 - Kautilya.pdf"]  # indexed name unchanged
    assert label["module"] == "DFA-SE" and "Kautilya and the Mandala" in label["title"]


def test_retire_and_replace(home: Path) -> None:
    fake = Fake([pdf("a", "CS22 - A.pdf"), pdf("b", "CS23 - B.pdf")])
    sync.run(fake.deps())
    fake.files = [pdf("b", "CS23 - B.pdf", md5="m2")]  # a deleted, b's content changed
    fake.kb_add_calls.clear()
    summary = sync.run(fake.deps())
    files = labels("DFA")
    assert files["CS22 - A.pdf"]["retired"] is True and files["CS23 - B.pdf"]["retired"] is True
    assert fake.kb_add_calls == [("DFA", ["CS23 - B (2).pdf"])]
    assert summary["retired"] == 1 and summary["replaced"] == 1


def test_indexer_crash_is_retried_without_retranscribing(home: Path) -> None:  # [RF5]
    fake = Fake([pdf("a", "CS22 - A.pdf"), mp4()])
    fake.fail_kb_add = 1
    summary = sync.run(fake.deps())
    assert summary["failed"] == 2 and {e.status for e in ledger().entries.values()} == {"failed"}
    summary = sync.run(fake.deps())
    assert summary["added"] == 2 and fake.transcribed == ["media.mp4"]  # transcript reused
    assert fake.kb_add_calls == [("DFA", ["CS22 - A.pdf", "Webinar - CS22 - Concept Cluster I - Kajari Kamal.md"])]


def test_one_bad_file_does_not_stop_the_sync(home: Path) -> None:  # [RF2]
    fake = Fake([pdf("a", "CS22 - A.pdf"), DriveFile(id="p", name="slides.pptx", path=AS + ("Readings",), mime="x/pptx"),
                 mp4()])
    def broken(*a, **k):
        raise RuntimeError("Sarvam down and no Zoom transcript")
    deps = fake.deps()
    deps.transcribe = broken
    summary = sync.run(deps)
    entries = ledger().entries
    assert (entries["a"].status, entries["p"].status, entries["r1"].status) == ("live", "skipped", "failed")
    assert entries["p"].error == "unsupported type .pptx" and summary["skipped"] == 1


def test_busy_lock_and_dry_run(home: Path) -> None:
    fake = Fake([pdf("a", "CS22 - A.pdf")])
    assert sync.run(fake.deps(), dry_run=True)["add"] == 1 and fake.kb_add_calls == []
    with sync.lock() as got:
        assert got and sync.run(fake.deps()) == {"busy": True}


def test_curated_labels_survive_first_relabel(home: Path) -> None:
    path = catalog.sources_path("DFA")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"files": {"CS1 - A.pdf": {"kind": "pdf", "title": "Hand-made title", "url": "https://x",
                                                             "corpus": "Anticipating the Unintended"}}}))
    led = Ledger(sync.library_root() / "ledger.json")
    from deeptutor.yaxa.library.ledger import seed
    seed(led, {"a": {"path": "/".join(AS + ("Readings", "CS1 - A.pdf")), "kb": "DFA", "indexed_as": "CS1 - A.pdf", "kind": "file"}},
         md5s={"a": "m1"})
    led.save()
    summary = sync.run(Fake([pdf("a", "CS1 - A.pdf")]).deps())
    label = labels("DFA")["CS1 - A.pdf"]
    assert summary["relabelled"] == 1
    assert (label["title"], label["url"], label["drive_id"], label["module"]) == ("Hand-made title", "https://x", "a", "DFA-AS")
    assert label["corpus"] == "Anticipating the Unintended"  # curated corpus survives too


def test_nightly_run_is_due_once_after_the_hour_ist() -> None:
    from datetime import datetime, timezone

    from deeptutor.yaxa.library.__main__ import due
    utc = lambda h, m=0, d=29: datetime(2026, 10, d, h, m, tzinfo=timezone.utc)  # noqa: E731
    # 02:00 IST == 20:30 UTC the previous day
    assert not due(utc(20, 0, 28), last_finished="", hour_ist=2)            # 01:30 IST: too early
    assert due(utc(20, 45, 28), last_finished="", hour_ist=2)               # 02:15 IST, never ran
    assert not due(utc(21, 0, 28), last_finished="2026-10-28T20:40:00+00:00", hour_ist=2)  # ran tonight
    assert due(utc(21, 0, 29), last_finished="2026-10-28T20:40:00+00:00", hour_ist=2)      # next night
