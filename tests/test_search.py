from datetime import UTC, datetime, timedelta

import pytest

from fakes import World, unit_vector
from team_docs import chunk, search
from team_docs.search import TOTAL_CHARS, fts_query, fuse


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    world = World()
    world.run()
    return world.index(tmp_path_factory.mktemp("index"))


def titles(results):
    return [result["title"] for result in results]


def test_fts_query_ors_words_and_quotes_identifiers():
    assert fts_query("How do I roll back INV-124?") == '"INV 124" OR "roll" OR "back" OR "inv" OR "124"'
    assert fts_query("what is the") is None


def test_keyword_search_finds_exact_names(index):
    results = search.search(index, "invalid_cursor", method="keyword", top_k=3)
    assert titles(results)[0] == "ADR-006 Cursor pagination for the item list"
    assert results[0]["keyword_rank"] == 1 and results[0]["vector_rank"] is None


def test_vector_search_ranks_by_similarity(index):
    row = index.db.execute(
        "SELECT c.id, c.heading, c.text, p.title FROM chunks c JOIN pages p USING (page_id)"
    ).fetchone()
    target = unit_vector(chunk.index_text(row["title"], chunk.Chunk(row["heading"], row["text"])))
    results = search.search(index, "anything", method="vector", top_k=3, embed=lambda question: target)
    assert results[0]["chunk_id"] == row["id"] and results[0]["vector_rank"] == 1


def test_hybrid_without_embeddings_is_keyword_search(index):
    keyword = search.search(index, "roll back a deploy", method="keyword")
    hybrid = search.search(index, "roll back a deploy", method="hybrid", embed=None)
    assert [r["chunk_id"] for r in hybrid] == [r["chunk_id"] for r in keyword]


def test_fusion_rewards_chunks_that_both_methods_rank():
    assert fuse([[1, 2, 3], [3, 1]]) == [1, 3, 2]
    assert fuse([[], [7]]) == [7]


def test_at_most_two_chunks_per_page(index):
    results = search.search(index, "deploy dev stack lambda logs", method="keyword", top_k=10)
    per_page = {}
    for result in results:
        per_page[result["page_id"]] = per_page.get(result["page_id"], 0) + 1
    assert max(per_page.values()) <= 2


def test_results_carry_their_source_and_fit_the_budget(index):
    results = search.search(index, "deploy", method="keyword", top_k=10)
    assert results
    first = results[0]
    assert first["url"].startswith("https://example.atlassian.net/wiki/spaces/INV/pages/")
    assert {"version", "edited_at", "synced_at", "flags", "hidden_chars"} <= set(first)
    assert sum(len(result["text"]) for result in results) <= TOTAL_CHARS + 10 * len("\n```\n[…]")


def test_trimmed_text_closes_its_code_block():
    text = "Run this:\n\n```bash\n" + "\n".join(f"echo {n}" for n in range(500)) + "\n```"
    trimmed, cut = search._trim(text, 200)
    assert cut and trimmed.endswith("```\n[…]") and trimmed.count("```") == 2


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def state(**fields):
    return {"last_success_at": (NOW - timedelta(minutes=5)).isoformat(), "token_expires": "2027-01-17", **fields}


def test_no_warnings_when_all_is_well():
    assert search.warnings(state(), NOW) == []


def test_never_synced():
    assert search.warnings({}, NOW) == ["WARNING: no sync has finished yet, so the index may be empty or incomplete."]


def test_stale_index():
    notes = search.warnings(state(last_success_at=(NOW - timedelta(hours=2, minutes=10)).isoformat()), NOW)
    assert notes == [
        "WARNING: the last successful sync was 2 h 10 min ago (2026-10-19 09:50 UTC). Results may be out of date."
    ]


def test_token_expiry():
    assert search.warnings(state(token_expires="2026-10-28"), NOW) == [
        "WARNING: the Confluence read token expires on 2026-10-28 (in 9 days). When it stops working, the sync stops."
    ]
    assert "expired on 2026-10-18" in search.warnings(state(token_expires="2026-10-18"), NOW)[0]


def test_last_run_problems():
    last_run = {
        "error": "ConfluenceError: HTTP 401: Unauthorized",
        "held": ["Deploy to dev", "Error codes"],
        "errors": [{"title": "Broken page", "error": "KeyError"}],
        "embedding_capped": True,
    }
    notes = search.warnings(state(last_run=last_run), NOW)
    assert notes[0] == "WARNING: the last sync run failed: ConfluenceError: HTTP 401: Unauthorized"
    assert "2 pages left Confluence in one run" in notes[1] and "Deploy to dev, Error codes" in notes[1]
    assert notes[2].startswith("NOTE: 1 pages could not be updated") and "Broken page" in notes[2]
    assert "embedding limit" in notes[3]
