"""Section authors in multi-author newsletter editions, and author labels in prompts."""

from __future__ import annotations

from deeptutor.yaxa import authors, prompting
from deeptutor.yaxa.catalog import Faculty

EDITION = """\
# #118 All Counting is Political

- Authors: Pranay Kotasthane & RSJ (co-written newsletter, Anticipating the Unintended)
- Date: 2021-03-28
- Source: https://publicpolicy.substack.com/p/118-all-counting-is-political

This newsletter is really a public policy thought-letter about frameworks and mental models.
India Policy Watch #1: The Truth Is Not Out There
Insights on burning policy issues in India
- RSJ
There aren't enough interpretive efforts done by scholars. Translation isn't interpretation. Also, there's more.
Reading list:
- Three Truths Of Ideology
- Tax Base Problem
India Policy Watch #2: Census 2021
Insights on burning policy issues in India
- Pranay Kotasthane
Census as a Measure of State Capacity. The census is the state's most basic act of seeing its people.
… the powerful play goes on, and you may contribute a verse.
-- Walt Whitman
What is a republic? How do markets work? Still Pranay's section.
PolicyWTF: Digital Trade
— Sridhar Krishna & Pranay Kotasthane
India has been at loggerheads with the developed nations at the WTO.
Matsyanyaya: Old Section
— Raghu Sanjaylal Jaitley
The fish eat the fish.
"""


def test_sections_found_in_order_with_list_and_quote_lines_skipped():
    names = [a for _, a in authors.parse_sections(EDITION)]
    assert names == ["RSJ", "Pranay Kotasthane", "Sridhar Krishna & Pranay Kotasthane", "RSJ"]


def test_author_of_passage_is_nearest_author_line_above_it():
    assert authors.author_at(EDITION, "Translation isn't interpretation. Also, there's more.") == "RSJ"
    assert authors.author_at(EDITION, "Census as a Measure of State Capacity. The census is") == "Pranay Kotasthane"
    assert authors.author_at(EDITION, "What is a republic? How do markets work?") == "Pranay Kotasthane"
    assert authors.author_at(EDITION, "India has been at loggerheads with the developed") == "Sridhar Krishna & Pranay Kotasthane"


def test_whitespace_differences_between_chunk_and_file_still_match():
    chunk = "Translation   isn't\ninterpretation.  Also, there's more."
    assert authors.author_at(EDITION, chunk) == "RSJ"


def test_intro_before_any_author_line_and_unknown_text_give_none():
    assert authors.author_at(EDITION, "This newsletter is really a public policy thought-letter") is None
    assert authors.author_at(EDITION, "text that is not in the file at all, anywhere") is None
    assert authors.author_at("No author lines here.\nJust prose about policy.", "Just prose about policy.") is None


def test_byline_wording():
    assert authors.byline("RSJ") == "by RSJ"
    assert authors.byline("Sridhar Krishna & Pranay Kotasthane") == "co-written by Sridhar Krishna & Pranay Kotasthane"


def _p(**kw):
    base = {"title": "118 All Counting is Political", "text": "Translation isn't interpretation.", "kb": "FACULTY-PRANAY", "byline": ""}
    return {**base, **kw}


def test_passages_carry_author_label_even_without_a_faculty_persona():
    block = prompting.number_passages([_p(byline="by RSJ")])
    assert "[by RSJ]" in block


def test_faculty_library_passage_without_byline_is_labelled_with_its_owner():
    block = prompting.number_passages([_p(kb="FACULTY-NITIN", byline="", corpus="Nitin Pai's writing")])
    assert "[by Nitin Pai]" in block


def test_course_reading_without_author_says_so():
    block = prompting.number_passages([_p(kb="GCPP101", byline="", corpus="Economic Reasoning")])
    assert "[author not stated" in block


def test_persona_sees_other_authors_by_name():
    pranay = Faculty(slug="pranay-kotasthane", name="Pranay Kotasthane", kb="FACULTY-PRANAY")
    block = prompting.number_passages([_p(byline="by RSJ")], pranay)
    assert "[by RSJ]" in block


def test_system_prompt_forbids_guessing_authors():
    system = prompting.build_system(profile={}, learner_name="", module=None, unit=None, faculty=None, socratic=False)
    assert "never guess" in system.lower()


def test_retrieve_credits_each_passage_to_its_article_author(tmp_path, monkeypatch):
    import asyncio

    from deeptutor.yaxa import grounding
    from deeptutor.yaxa.catalog import SourceInfo

    raw = tmp_path / "FACULTY-PRANAY" / "raw"
    raw.mkdir(parents=True)
    (raw / "2021-03-28-118-all-counting-is-political.md").write_text(EDITION)
    monkeypatch.setattr(grounding, "admin_kb_base_dir", lambda: tmp_path)

    class FakeRAG:
        def __init__(self, **kw):
            pass

        async def search(self, query, kb_name, top_k):
            return {"sources": [
                {"source": "2021-03-28-118-all-counting-is-political.md", "score": 0.9,
                 "text": "There aren't enough interpretive efforts done by scholars. Translation isn't interpretation. Also, there's more."},
                {"source": "2021-03-28-118-all-counting-is-political.md", "score": 0.8,
                 "text": "This newsletter is really a public policy thought-letter about frameworks and mental models. India Policy Watch"},
            ]}

    monkeypatch.setattr(grounding, "RAGService", FakeRAG)
    monkeypatch.setattr(grounding, "source_info", lambda kb, f: SourceInfo(byline="co-written by Pranay Kotasthane & RSJ", kind="note"))
    got = asyncio.run(grounding.retrieve("FACULTY-PRANAY", "translation", 4))
    assert [p["byline"] for p in got] == ["by RSJ", "co-written by Pranay Kotasthane & RSJ"]
