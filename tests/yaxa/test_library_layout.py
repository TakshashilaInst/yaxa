"""Where a file in the shared Drive library belongs: library, module, unit, labels."""

from __future__ import annotations

from deeptutor.yaxa.catalog import get_catalog
from deeptutor.yaxa.library.layout import Placement, place

CAT = get_catalog(fresh=True)
DFA_AS = ["GCPP", "DFA Defence and Foreign Affairs", "DFA-AS Introduction to Arthashastra"]
PDF, MP4 = "application/pdf", "video/mp4"


def test_reading_takes_library_module_and_code() -> None:
    p = place(DFA_AS + ["Readings"], "CS22 - Kautilya_and_the  Mandala.pdf", PDF, CAT)
    assert isinstance(p, Placement)
    assert (p.kb, p.kind, p.module, p.unit, p.corpus) == ("DFA", "reading", "DFA-AS", "CS22", "Course readings")
    assert p.title == "CS22 Introduction to Arthashastra: Kautilya and the Mandala"


def test_recording_has_speaker_and_cohort() -> None:
    p = place(DFA_AS + ["Recordings", "DFA26 Jun 2026"], "CS22 - Concept Cluster I - Kajari Kamal.mp4", MP4, CAT)
    assert (p.kind, p.unit, p.speaker, p.cohort) == ("recording", "CS22", "Kajari Kamal", "DFA26 (Jun 2026)")
    assert p.corpus == "Webinar recording, DFA26 (Jun 2026)"
    assert p.title == "Webinar: CS22 Concept Cluster I, Kajari Kamal"


def test_recording_without_code() -> None:
    p = place(DFA_AS + ["Recordings", "DFA25 Feb 2026"], "Guest talk - Shivshankar Menon.mp4", MP4, CAT)
    assert (p.unit, p.speaker, p.title) == ("", "Shivshankar Menon", "Webinar: Guest talk, Shivshankar Menon")


def test_recording_with_unit_number_and_no_speaker() -> None:
    p = place(DFA_AS + ["Recordings", "DFA26 Jun 2026"], "U02 - Market Failures.m4a", "audio/mp4", CAT)
    assert (p.unit, p.speaker, p.title) == ("U02", "", "Webinar: U02 Market Failures")


def test_zoom_transcript_is_its_own_kind() -> None:
    p = place(DFA_AS + ["Recordings", "DFA26 Jun 2026"], "CS22 - Concept Cluster I - Kajari Kamal.vtt", "text/vtt", CAT)
    assert p.kind == "transcript"


def test_core_app_and_capsule_modules() -> None:
    core = place(["GCPP", "Core", "GCPP-ER1 Economic Reasoning I", "Readings"], "CP21 - Readings (A).pdf", PDF, CAT)
    app = place(["GCPP", "APP Advanced Public Policy", "APP-ER2 Economic Reasoning II", "Readings"], "CP50 - Readings.pdf", PDF, CAT)
    cap = place(["Expert Capsules", "Public Finance", "GCPP173 Public Finance and Indian Development Policy", "Readings"],
                "x.pdf", PDF, CAT)
    assert (core.kb, app.kb, app.module, cap.kb) == ("GCPP-ER1", "APP", "APP-ER2", "GCPP173")


def test_faculty_writing() -> None:
    p = place(["Faculty", "Pranay Kotasthane", "Writings"], "2026-03-08-of-wars-and-races.md", "text/markdown", CAT)
    assert (p.kb, p.kind, p.corpus) == ("FACULTY-PRANAY", "writing", "Pranay Kotasthane's writing")


def test_excluded_folders_are_skipped_silently() -> None:
    assert place(["_Retired"], "x.pdf", PDF, CAT) is None
    assert place(DFA_AS + ["_Not for Yaxa"], "x.pdf", PDF, CAT) is None


def test_problems_come_back_as_reasons() -> None:  # [RF2]
    assert place(["GCPP", "Core", "GCPP-XX Nothing"], "x.pdf", PDF, CAT) == "unknown module GCPP-XX"
    assert place(["GCPP", "Core"], "x.pdf", PDF, CAT) == "not inside a module folder"
    assert place(["Faculty", "Someone Else"], "a.md", "text/markdown", CAT) == "no faculty library for Someone Else"
    pptx = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert place(DFA_AS + ["Readings"], "slides.pptx", pptx, CAT) == "unsupported type .pptx"
    assert place(DFA_AS + ["Readings"], "Notes", "application/vnd.google-apps.document", CAT) == (
        "unsupported type Google Doc (download it as PDF and upload that)")
    assert place(DFA_AS + ["Readings"], "x.pdf", "shortcut/unreadable", CAT) == "shortcut to a file Yaxa can't open"


def test_track_level_file_goes_to_the_track_library() -> None:
    p = place(["GCPP", "APP Advanced Public Policy"], "APP - Module guide.md", "text/markdown", CAT)
    assert isinstance(p, Placement) and (p.kb, p.kind, p.module) == ("APP", "reading", "")
    assert place(["GCPP", "Core"], "x.pdf", PDF, CAT) == "not inside a module folder"  # core modules have separate libraries


def test_mixed_case_module_folder() -> None:
    p = place(["GCPP", "Core", "GCPP-Fundamentals Policy Analysis and Concepts", "Readings"], "CP10 - Readings.pdf", PDF, CAT)
    assert p.module == "GCPP-Fundamentals" and p.kb == "GCPP-PAC" and p.unit == "CP10"


def test_old_module_code_still_maps_through_alias() -> None:
    p = place(["GCPP", "Core", "GCPP-PAC Policy Analysis and Concepts", "Readings"], "CP10 - Readings.pdf", PDF, CAT)
    assert p.module == "GCPP-Fundamentals" and p.kb == "GCPP-PAC"
