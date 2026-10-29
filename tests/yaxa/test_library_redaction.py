"""Names-only redaction for library transcripts, and the name gate that holds doubtful ones."""

from __future__ import annotations

import logging
from pathlib import Path

from deeptutor.yaxa.library.redaction import apply_review, learn, redact_segments, student_names

PUBLIC = {"full": ["Deepak Lal", "Ajay Shah", "Nikita Khrushchev"], "single": ["Keynes"], "other": ["Tamil Nadu"]}
HEADER = "# Webinar transcript: Concept Cluster I\n\n- Speaker: Kajari Kamal"


def seg(t: float, text: str, speaker: str = "") -> dict:
    return {"start": t, "end": t + 3, "text": text, "speaker": speaker}


def test_zoom_participant_name_removed_everywhere_question_kept() -> None:  # [RF4]
    r = redact_segments(
        [seg(0, "Good evening. Thanks Ravi, that is a good question.", "Kajari Kamal"),
         seg(65, "Is saptanga still relevant today?", "ravi.k"),
         seg(70, "Let me answer that, Ravi.", "Kajari Kamal")],
        HEADER, "Kajari Kamal", PUBLIC, set())
    assert "ravi" not in r.markdown.lower()
    assert "Is saptanga still relevant today?" in r.markdown
    assert "Participant:" in r.markdown and "Kajari Kamal:" in r.markdown
    assert "ravi" in {n.lower() for n in r.removed}
    assert r.flags == []


def test_full_display_name_from_zoom_removed() -> None:  # [RF4]
    r = redact_segments([seg(0, "Ananya Krishnan here, quick question", "Ananya Krishnan"),
                         seg(5, "Yes Ananya, go on.", "Kajari Kamal")], HEADER, "Kajari Kamal", PUBLIC, set())
    assert "Ananya" not in r.markdown and "Krishnan" not in r.markdown


def test_public_author_kept_but_known_student_flagged() -> None:
    r = redact_segments([seg(0, "As Deepak Lal argues, and as Deepak said earlier in class.")],
                        HEADER, "Prakash Menon", PUBLIC, {"Deepak"})
    assert "Deepak Lal" in r.markdown
    assert [f["name"] for f in r.flags] == ["Deepak"]
    assert "Deepak said" in r.flags[0]["context"] and r.flags[0]["at"] == "00:00:00"


def test_allowed_name_is_not_flagged_again() -> None:
    r = redact_segments([seg(0, "As Deepak said earlier.")], HEADER, "Prakash Menon", PUBLIC, {"Deepak"}, allow={"Deepak"})
    assert r.flags == [] and "Deepak said" in r.markdown


def test_known_student_names_replaced_without_speaker_labels() -> None:
    r = redact_segments([seg(0, "Meera made a fair point about Keynes.")], HEADER, "Anupam Manur", PUBLIC, {"Meera"})
    assert "Meera" not in r.markdown and "Keynes" in r.markdown


def test_lecturer_and_faculty_names_are_kept() -> None:
    r = redact_segments([seg(0, "As Pranay Kotasthane and Nitin Pai have written.", "Kajari Kamal")],
                        HEADER, "Kajari Kamal", PUBLIC, set())
    assert "Pranay Kotasthane" in r.markdown and "Nitin Pai" in r.markdown


def test_header_names_the_engine_and_body_has_timestamps() -> None:
    r = redact_segments([seg(62, "Hello.", "Kajari Kamal")], HEADER, "Kajari Kamal", PUBLIC, set(),
                        engine="Sarvam (saaras:v4), speakers from Zoom")
    assert "Sarvam (saaras:v4), speakers from Zoom" in r.markdown and "[00:01:02] Kajari Kamal: Hello." in r.markdown


def test_apply_review() -> None:
    md = "# W\n\n[00:00:00] as Deepak said, and Deepak's point"
    assert apply_review(md, {"Deepak": "remove"}) == "# W\n\n[00:00:00] as a participant said, and a participant's point"
    assert apply_review(md, {"Deepak": "keep"}) == md


def test_student_names_and_learning(tmp_path: Path) -> None:
    secrets = tmp_path / "student-names.txt"
    secrets.write_text("# cohort\nAnanya Krishnan, Ravi;Meera\n")
    learned = tmp_path / "learned.txt"
    learn(learned, {"Rohit", "ravi"})
    names = student_names(secrets, ["Sita Raman", "demo"], learned)
    assert {"Ananya", "Krishnan", "Ravi", "Meera", "Sita", "Raman", "Rohit"} <= names
    assert "demo" not in names and "cohort" not in names
    assert oct(learned.stat().st_mode & 0o777) == "0o600"


def test_names_never_logged(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    redact_segments([seg(0, "Thanks Ravi.", "Kajari Kamal"), seg(5, "Hi", "ravi.k")], HEADER, "Kajari Kamal", PUBLIC, {"Meera"})
    assert "ravi" not in caplog.text.lower() and "meera" not in caplog.text.lower()
