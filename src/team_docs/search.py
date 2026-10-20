"""Ranking over the index, and the warnings that go with every answer.

Three methods: keyword (SQLite FTS5 with BM25), vector (cosine similarity of Titan embeddings)
and hybrid, which fuses the two rankings with reciprocal rank fusion (RRF). The evaluation runs
all three; the tool uses hybrid.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from .index import Index

METHODS = ("keyword", "vector", "hybrid")
CANDIDATES = 50  # taken from each method before fusion
RRF_K = 60
PER_PAGE = 2  # at most this many chunks of one page in the results
MAX_TOP_K = 10
TOTAL_CHARS = 16_000  # about 4,000 tokens for all results together
CHUNK_CHARS = 3_000
KEYWORD_WEIGHTS = "2.0, 2.0, 1.0"  # BM25 weights of the title, heading and text columns
STALE_AFTER = timedelta(minutes=30)
TOKEN_WARNING_DAYS = 14

WORD = re.compile(r"\w+")
IDENTIFIER = re.compile(r"\w+(?:[-./:]\w+)+")  # INV-124, ap-southeast-2, items/42
# fmt: off
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do", "does", "for", "from", "has",
    "have", "how", "i", "if", "in", "is", "it", "its", "me", "my", "of", "on", "or", "our", "should", "so", "that",
    "the", "their", "them", "then", "there", "these", "this", "to", "us", "was", "we", "were", "what", "when",
    "where", "which", "who", "why", "will", "with", "would", "you", "your",
})
# fmt: on


def search(
    index: Index,
    question: str,
    *,
    method: str = "hybrid",
    top_k: int = 5,
    embed: Callable[[str], np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    keyword_ids = keyword(index, question) if method in ("keyword", "hybrid") else []
    vector_ids: list[int] = []
    if method in ("vector", "hybrid") and embed is not None and index.has_vector.any():
        vector_ids = vector(index, embed(question))
    if method == "keyword":
        ranked = keyword_ids
    elif method == "vector":
        ranked = vector_ids
    else:
        ranked = fuse([keyword_ids, vector_ids])
    chosen = diversify(index, ranked, top_k)
    limit = min(CHUNK_CHARS, TOTAL_CHARS // max(top_k, 1))
    return [_result(index, chunk_id, rank, limit, keyword_ids, vector_ids) for rank, chunk_id in enumerate(chosen, 1)]


def fts_query(question: str) -> str | None:
    """Every word of the question ORed together, and identifiers such as INV-124 also as phrases."""
    terms = [" ".join(WORD.findall(token)) for token in IDENTIFIER.findall(question)]
    terms += [word for word in WORD.findall(question.lower()) if word not in STOPWORDS]
    quoted = [f'"{term}"' for term in dict.fromkeys(terms) if term]
    return " OR ".join(quoted) or None


def keyword(index: Index, question: str, limit: int = CANDIDATES) -> list[int]:
    query = fts_query(question)
    if query is None:
        return []
    rows = index.db.execute(
        f"SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, {KEYWORD_WEIGHTS}) LIMIT ?",
        (query, limit),
    )
    return [row[0] for row in rows]


def vector(index: Index, query_vector: np.ndarray, limit: int = CANDIDATES) -> list[int]:
    """Chunk ids by cosine similarity. Vectors are normalized, so this is a dot product."""
    scores = np.where(index.has_vector, index.vectors @ query_vector, -np.inf)
    order = np.argsort(-scores, kind="stable")[:limit]
    return [int(row) + 1 for row in order if np.isfinite(scores[row])]


def fuse(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion: each ranking adds 1 / (k + rank) to a chunk's score."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


def diversify(index: Index, ranked: list[int], top_k: int, per_page: int = PER_PAGE) -> list[int]:
    """The best `top_k` chunks, with at most `per_page` from any one page."""
    page_of = dict(index.db.execute("SELECT id, page_id FROM chunks").fetchall())
    taken: list[int] = []
    per: dict[str, int] = {}
    for chunk_id in ranked:
        page = page_of[chunk_id]
        if per.get(page, 0) < per_page:
            taken.append(chunk_id)
            per[page] = per.get(page, 0) + 1
            if len(taken) == top_k:
                break
    return taken


def warnings(state: dict[str, Any], now: datetime) -> list[str]:
    """What the agent and the person behind it should know before trusting the results."""
    notes: list[str] = []
    last_success = _time(state.get("last_success_at"))
    if last_success is None:
        notes.append("WARNING: no sync has finished yet, so the index may be empty or incomplete.")
    elif now - last_success > STALE_AFTER:
        notes.append(
            f"WARNING: the last successful sync was {ago(now - last_success)} ago ({utc(last_success)}). "
            "Results may be out of date."
        )
    last_run = state.get("last_run") or {}
    if last_run.get("error"):
        notes.append(f"WARNING: the last sync run failed: {last_run['error']}")
    if held := last_run.get("held"):
        notes.append(
            f"WARNING: {len(held)} pages left Confluence in one run, more than the sync removes without a "
            f"person checking, so they are still in the index: {_titles(held)}."
        )
    if failed := last_run.get("errors"):
        notes.append(
            f"NOTE: {len(failed)} pages could not be updated in the last sync and may be out of date: "
            f"{_titles([page['title'] for page in failed])}."
        )
    if last_run.get("embedding_capped"):
        notes.append(
            "NOTE: the monthly embedding limit was reached; pages changed since then are found by keywords only."
        )
    expires = _date(state.get("token_expires"))
    if expires is not None and (expires - now.date()).days <= TOKEN_WARNING_DAYS:
        days = (expires - now.date()).days
        when = f"expired on {expires}" if days < 0 else f"expires on {expires} (in {days} days)"
        notes.append(f"WARNING: the Confluence read token {when}. When it stops working, the sync stops.")
    return notes


def ago(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h {minutes % 60} min"
    return f"{minutes // (24 * 60)} days"


def utc(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _result(
    index: Index, chunk_id: int, rank: int, limit: int, keyword_ids: list[int], vector_ids: list[int]
) -> dict[str, Any]:
    row = index.db.execute(
        "SELECT c.page_id, c.heading, c.text, c.flags, p.title, p.url, p.version, p.edited_at, p.synced_at, "
        "p.hidden_chars FROM chunks c JOIN pages p ON p.page_id = c.page_id WHERE c.id = ?",
        (chunk_id,),
    ).fetchone()
    text, truncated = _trim(row["text"], limit)
    return {
        "rank": rank,
        "chunk_id": chunk_id,
        "page_id": row["page_id"],
        "title": row["title"],
        "heading": row["heading"],
        "url": row["url"],
        "version": row["version"],
        "edited_at": row["edited_at"],
        "synced_at": row["synced_at"],
        "hidden_chars": row["hidden_chars"],
        "flags": json.loads(row["flags"]),
        "text": text,
        "truncated": truncated,
        "keyword_rank": keyword_ids.index(chunk_id) + 1 if chunk_id in keyword_ids else None,
        "vector_rank": vector_ids.index(chunk_id) + 1 if chunk_id in vector_ids else None,
    }


def _trim(text: str, limit: int) -> tuple[str, bool]:
    """At most `limit` characters, cut at a line break, with any open code block closed."""
    if len(text) <= limit:
        return text, False
    cut = text.rfind("\n", 0, limit)
    cut = cut if cut > limit // 2 else limit
    kept = text[:cut].rstrip()
    if kept.count("```") % 2:
        kept += "\n```"
    return kept + "\n[…]", True


def _titles(titles: list[str], shown: int = 5) -> str:
    more = f" and {len(titles) - shown} more" if len(titles) > shown else ""
    return ", ".join(titles[:shown]) + more


def _time(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) and value else None
    except ValueError:
        return None
