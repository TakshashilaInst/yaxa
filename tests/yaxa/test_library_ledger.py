"""Library ledger: what the sync has done with each Drive file, and what to do next."""

from __future__ import annotations

from pathlib import Path

from deeptutor.yaxa.library.drive import DriveFile
from deeptutor.yaxa.library.layout import Placement
from deeptutor.yaxa.library.ledger import Entry, Ledger, diff, indexed_name, seed

READ = Placement(kb="DFA", kind="reading", module="DFA-AS", unit="CS22", title="CS22 x: A", corpus="Course readings")
REC = Placement(kb="DFA", kind="recording", module="DFA-AS", unit="CS22", cohort="DFA26 (Jun 2026)",
                title="Webinar: CS22 A, K", speaker="K", corpus="Webinar recording, DFA26 (Jun 2026)")
VTT = Placement(kb="DFA", kind="transcript", module="DFA-AS", unit="CS22")
P = ("GCPP", "DFA Defence and Foreign Affairs", "DFA-AS Introduction to Arthashastra")


def f(id_, name, path=P + ("Readings",), md5="m1", mime="application/pdf"):
    return DriveFile(id=id_, name=name, path=path, mime=mime, md5=md5)


def ledger(tmp_path: Path, *entries: Entry) -> Ledger:
    led = Ledger(tmp_path / "ledger.json")
    led.entries = {e.drive_id: e for e in entries}
    return led


def kinds(actions):
    return [(a.kind, (a.file or a.entry).id if a.file else a.entry.drive_id) for a in actions]


def test_new_file_is_added(tmp_path: Path) -> None:
    acts = diff([f("a", "CS22 - A.pdf")], {"a": READ}, ledger(tmp_path))
    assert kinds(acts) == [("add", "a")] and acts[0].placement == READ


def test_rename_in_same_library_only_relabels(tmp_path: Path) -> None:  # [RF1]
    live = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="CS22 - A.pdf", md5="m1", path="old/CS22 - A.pdf", status="live")
    moved = Placement(**{**READ.__dict__, "module": "DFA-SE", "title": "CS22 y: A"})
    acts = diff([f("a", "CS22 - A (new name).pdf")], {"a": moved}, ledger(tmp_path, live))
    assert kinds(acts) == [("relabel", "a")]


def test_unchanged_file_does_nothing(tmp_path: Path) -> None:
    file = f("a", "CS22 - A.pdf")
    live = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="CS22 - A.pdf", md5="m1",
                 path="/".join(file.path + (file.name,)), status="live", placement=READ.__dict__)
    assert diff([file], {"a": READ}, ledger(tmp_path, live)) == []


def test_move_to_another_library_retires_and_adds(tmp_path: Path) -> None:
    live = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="CS22 - A.pdf", md5="m1", status="live")
    tp = Placement(**{**READ.__dict__, "kb": "TP", "module": "TP-HTG"})
    assert kinds(diff([f("a", "CS22 - A.pdf")], {"a": tp}, ledger(tmp_path, live))) == [("retire", "a"), ("add", "a")]


def test_changed_content_is_replaced(tmp_path: Path) -> None:
    live = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="CS22 - A.pdf", md5="m1", status="live")
    assert kinds(diff([f("a", "CS22 - A.pdf", md5="m2")], {"a": READ}, ledger(tmp_path, live))) == [("replace", "a")]


def test_gone_or_excluded_is_retired(tmp_path: Path) -> None:
    a = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="A.pdf", status="live")
    b = Entry(drive_id="b", kb="DFA", kind="reading", indexed_as="B.pdf", status="live")
    gone_already = Entry(drive_id="c", kb="DFA", kind="reading", indexed_as="C.pdf", status="retired")
    acts = diff([f("b", "B.pdf", path=("_Retired",))], {"b": None}, ledger(tmp_path, a, b, gone_already))
    assert sorted(kinds(acts)) == [("retire", "a"), ("retire", "b")]


def test_unusable_file_is_skipped_with_reason(tmp_path: Path) -> None:  # [RF2]
    acts = diff([f("a", "x.pptx")], {"a": "unsupported type .pptx"}, ledger(tmp_path))
    assert kinds(acts) == [("skip", "a")] and acts[0].reason == "unsupported type .pptx"


def test_skip_is_not_repeated_for_the_same_reason(tmp_path: Path) -> None:
    skipped = Entry(drive_id="a", kb="", kind="", indexed_as="", md5="m1", status="skipped", error="unsupported type .pptx")
    assert diff([f("a", "x.pptx")], {"a": "unsupported type .pptx"}, ledger(tmp_path, skipped)) == []


def test_interrupted_or_failed_entry_is_retried(tmp_path: Path) -> None:  # [RF5]
    stuck = Entry(drive_id="a", kb="DFA", kind="reading", indexed_as="CS22 - A.pdf", md5="m1", status="processing")
    failed = Entry(drive_id="b", kb="DFA", kind="reading", indexed_as="B.pdf", md5="m1", status="failed")
    acts = diff([f("a", "CS22 - A.pdf"), f("b", "B.pdf")], {"a": READ, "b": READ}, ledger(tmp_path, stuck, failed))
    assert sorted(kinds(acts)) == [("add", "a"), ("add", "b")]
    assert acts[0].entry is not None  # keeps the name it already reserved


def test_review_and_approved_entries_wait_for_people(tmp_path: Path) -> None:
    rev = Entry(drive_id="a", kb="DFA", kind="recording", indexed_as="W.md", md5="m1", status="review")
    assert diff([f("a", "x.mp4", mime="video/mp4")], {"a": REC}, ledger(tmp_path, rev)) == []
    ok = Entry(drive_id="b", kb="DFA", kind="recording", indexed_as="V.md", md5="m1", status="approved")
    assert kinds(diff([f("b", "y.mp4", mime="video/mp4")], {"b": REC}, ledger(tmp_path, ok))) == [("index", "b")]


def test_zoom_transcript_rides_with_its_recording(tmp_path: Path) -> None:
    rec_path = P + ("Recordings", "DFA26 Jun 2026")
    files = [f("r", "CS22 - A - K.mp4", path=rec_path, mime="video/mp4"), f("v", "CS22 - A - K.vtt", path=rec_path, mime="text/vtt")]
    acts = diff(files, {"r": REC, "v": VTT}, ledger(tmp_path))
    assert kinds(acts) == [("add", "r")] and acts[0].extra == {"vtt_id": "v"}


def test_save_load_round_trip_and_seed(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "ledger.json")
    fill = {"a": {"path": "GCPP/x/CS22 - A.pdf", "kb": "DFA", "indexed_as": "CS1 - A.pdf", "kind": "file"},
            "r": {"path": "GCPP/x/Recordings/DFA26 Jun 2026/A.mp4", "kb": "DFA", "indexed_as": "Webinar - A.md",
                  "kind": "recording", "source_id": "orig"}}
    assert seed(led, fill, md5s={"a": "m1", "r": "m2"}) == 2
    assert seed(led, fill, md5s={"a": "m1", "r": "m2"}) == 0  # idempotent
    led.save()
    again = Ledger(tmp_path / "ledger.json")
    again.load()
    a, r = again.entries["a"], again.entries["r"]
    assert (a.status, a.indexed_as, a.md5, a.kind, r.kind) == ("live", "CS1 - A.pdf", "m1", "reading", "recording")


def test_indexed_name_avoids_collisions() -> None:
    rec_file = f("r", "CS22 - Concept Cluster I - K.mp4", mime="video/mp4")
    assert indexed_name(READ, f("a", "CS22 - A.pdf"), set()) == "CS22 - A.pdf"
    assert indexed_name(READ, f("a", "CS22 - A.pdf"), {"CS22 - A.pdf"}) == "CS22 - A (2).pdf"
    assert indexed_name(REC, rec_file, set()) == "Webinar - CS22 - Concept Cluster I - K.md"
