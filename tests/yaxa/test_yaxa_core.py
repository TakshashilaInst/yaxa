"""Yaxa Learn: content catalog, per-user store, prompts and citation parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, prompting, store
from deeptutor.yaxa.api import _cited_numbers


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point Yaxa's data folder at a temp dir and reload content."""
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    yield
    catalog.get_catalog(fresh=True)


# ----------------------------------------------------------------- catalog
def test_every_programme_module_resolves() -> None:
    cat = catalog.get_catalog()
    assert {p.code for p in cat.programmes} >= {"GCPP", "PGP"}
    for prog in cat.programmes:
        for code in prog.module_codes():
            assert cat.module(code) is not None, f"{prog.code} references unknown {code}"


def test_gcpp_has_tracks_and_pgp_does_not() -> None:
    cat = catalog.get_catalog()
    gcpp, pgp = cat.programme("GCPP"), cat.programme("PGP")
    assert gcpp.tracks and not pgp.tracks
    app, tp = gcpp.module_codes("APP"), gcpp.module_codes("TP")
    core = ["GCPP-Fundamentals", "GCPP-ER1", "GCPP-COMM"]
    assert app[:3] == core and tp[:3] == core  # every track shares the core weeks
    assert "APP-ER2" in app and "APP-ER2" not in tp


def test_indexed_modules_have_units() -> None:
    cat = catalog.get_catalog()
    assert cat.module("GCPP-ER1").available and [u.id for u in cat.module("GCPP-ER1").units] == ["CP21", "CP22", "CP23", "CP24", "CP25"]
    assert cat.module("APP-ER2").kb == "APP"  # APP modules share one library
    for code, kb in {"TP-AI": "TP", "TP-HTG": "TP", "DFA-SSIR": "DFA", "DFA-SE": "DFA"}.items():
        mod = cat.module(code)
        assert mod.available and mod.kb == kb and mod.units  # track modules share one library each


def test_server_override_wins(tmp_path: Path) -> None:
    override = tmp_path / "data" / "yaxa" / "content"
    override.mkdir(parents=True)
    (override / "config.yaml").write_text("model_mode: per_user\n")
    assert catalog.get_catalog(fresh=True).settings.model_mode == "per_user"


# ------------------------------------------------------------------- store
def test_user_round_trip_and_profile_cleaning() -> None:
    user = store.load_user("u_test", display_name="Test")
    assert not user.onboarded
    user.profile = store.clean_profile({"current_role": "  Lecturer ", "bogus": "x", "field": ""})
    store.save_user(user)
    again = store.load_user("u_test")
    assert again.profile == {"current_role": "Lecturer"}
    assert again.onboarded


def test_unsafe_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        store.load_user("../etc/passwd")


def test_daily_turn_limit() -> None:
    user = store.load_user("u_limit")
    assert store.count_turn(user, 2) and store.count_turn(user, 2)
    assert not store.count_turn(user, 2)


def test_conversation_round_trip() -> None:
    conv = store.Conversation(user_id="u_c", module="GCPP102", title="Opportunity cost")
    conv.turns.append(store.Turn(role="user", content="What is opportunity cost?"))
    store.save_conversation(conv)
    assert store.load_conversation("u_c", conv.id).turns[0].content.startswith("What")
    assert store.list_conversations("u_c")[0]["title"] == "Opportunity cost"


# ----------------------------------------------------------------- prompts
def test_prompt_carries_profile_unit_persona_and_mode() -> None:
    cat = catalog.get_catalog()
    mod = cat.module("GCPP-ER1")
    fac = cat.faculty["pranay-kotasthane"]
    text = prompting.build_system(
        profile={"current_role": "Lecturer at NUS", "field": "AI & education policy"},
        learner_name="Karthik",
        module=mod,
        unit=mod.units[0],
        faculty=fac,
        socratic=True,
    )
    assert "Lecturer at NUS" in text and mod.units[0].title in text
    assert fac.label in text and "Socratic mode is ON" in text
    assert "better or worse" in text.lower()


def test_numbered_passages_mark_faculty_sources() -> None:
    fac = catalog.get_catalog().faculty["pranay-kotasthane"]
    block = prompting.number_passages(
        [
            {"kb": "GCPP102", "title": "Reader", "page": 79, "text": "Opportunity cost is..."},
            {"kb": fac.kb, "title": "Op-ed", "page": None, "text": "Subsidies..."},
        ],
        fac,
    )
    assert "[1] Reader, p. 79" in block
    assert "[2] Op-ed [by Pranay Kotasthane]" in block


def test_coauthored_passages_are_marked_as_joint_work() -> None:
    fac = catalog.get_catalog().faculty["pranay-kotasthane"]
    block = prompting.number_passages(
        [{"kb": fac.kb, "title": "Edition 300", "page": None, "text": "...",
          "byline": "co-written by Pranay Kotasthane & RSJ"}],
        fac,
    )
    assert "[1] Edition 300 [co-written by Pranay Kotasthane & RSJ]" in block
    system = prompting.build_system(profile={}, learner_name="", module=None, unit=None, faculty=fac, socratic=False)
    assert "joint work" in system


# --------------------------------------------------------------- citations
def test_cited_numbers_in_order_without_duplicates() -> None:
    answer = "Cost [2]. Again [2]. Both [1, 3]. Junk [x] [12]"
    assert _cited_numbers(answer) == [2, 1, 3, 12]


# ------------------------------------------------------------- page finding
def test_locate_page_finds_the_right_page(tmp_path: Path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    from deeptutor.yaxa.grounding import locate_page

    pages = [
        "Demand curves slope downward because of diminishing marginal utility for most goods.",
        "Opportunity cost is the value of the next highest valued alternative use of a resource.",
        "Fiscal federalism divides taxing powers between the Union and the States in India.",
    ]
    pdf = tmp_path / "reader.pdf"
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text * 3)
    doc.save(pdf)

    # A passage as a parser might return it: different whitespace and case.
    passage = "OPPORTUNITY cost is the value of the next   highest valued alternative use of a resource."
    assert locate_page(pdf, passage) == 2
    assert locate_page(pdf, "Completely unrelated words about cricket scores and monsoon rainfall.") is None


def test_titles_from_course_file_names() -> None:
    from deeptutor.yaxa.grounding import _title_from_file

    assert _title_from_file("GCPP102LU06 - RR01 - Introduction-Key-Concepts-in-Economic-Reasoning.pdf") == (
        "Introduction Key Concepts in Economic Reasoning",
        "LU06",
    )
    assert _title_from_file("GCPP102LU01 - RR01 - Economics - A Very Short Introduction (1).pdf") == (
        "Economics - A Very Short Introduction",
        "LU01",
    )
    assert _title_from_file("GCPP102 - Course outline.md") == ("GCPP102 - Course outline", "")
