"""The evaluation questions must match the corpus: real page titles, and facts the pages contain."""

import re

import pytest
from evals.common import has_fact, mentions, questions
from scripts.demo_docs import load_docs

from team_docs.search import STOPWORDS

QUESTIONS = questions()
DOCS = {doc.title: f"{doc.title}\n{doc.body}" for doc in load_docs("v1")}
KINDS = {"paraphrase", "exact", "multi", "none"}
AUTHORS = {"claude", "claude-low-overlap", "user"}
LOW_OVERLAP = 0.5  # at most this share of a low-overlap question's words may appear in its pages


def overlap(question: dict) -> float:
    """Share of the question's words, stop words aside, that also appear in its answer pages."""
    page_words = set(re.findall(r"[a-z0-9_]+", "\n".join(DOCS[title] for title in question["pages"]).lower()))
    words = [w for w in re.findall(r"[a-z0-9_]+", question["question"].lower()) if w not in STOPWORDS and len(w) > 1]
    return sum(word in page_words for word in words) / len(words)


def test_ids_are_unique_and_fields_complete():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    for question in QUESTIONS:
        assert question["by"] in AUTHORS, question["id"]
        assert question["kind"] in KINDS, question["id"]
        assert question["question"].strip(), question["id"]
        assert bool(question["pages"]) == (question["kind"] != "none"), question["id"]


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q["pages"]], ids=lambda q: q["id"])
def test_pages_exist_and_contain_the_facts(question):
    for title in question["pages"]:
        assert title in DOCS, f"no page titled {title!r}"
    text = "\n".join(DOCS[title] for title in question["pages"])
    for fact in question["facts"]:
        assert has_fact(text, fact), f"{question['id']}: {fact!r} is in none of its pages"


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q["by"] == "claude-low-overlap"], ids=lambda q: q["id"])
def test_low_overlap_questions_avoid_the_words_of_their_pages(question):
    assert overlap(question) <= LOW_OVERLAP


def test_whole_word_matching():
    assert mentions("Run gh run rerun <id>", "gh run rerun")
    assert not mentions("the guide", "ui")
    assert mentions("branch INV-123-stock", "INV-")
    assert mentions("files under .github/**", ".github")
