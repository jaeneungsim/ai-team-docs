#!/usr/bin/env python3
"""Retrieval evaluation: does each method put a page that answers the question in its top 5?

It downloads the index the search function is using right now, so it ranks exactly what the
tool ranks, with the same code. It also builds a copy of that index without the
"page title > section" prefix on each chunk, to measure what the prefix adds.

Methods: keyword (BM25), vector (Titan embeddings), hybrid (both, fused with RRF), and hybrid
without the prefix. Metrics: hit@5 (a right page among the top 5 sections) and MRR (1 / the
rank of the first right section). Questions the docs do not answer are left out of both.

    AWS_PROFILE=<sso-profile> .venv/bin/python evals/retrieval.py

The only cost is Titan embeddings for the questions and for the copy, a fraction of a cent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from common import RESULTS, download_index, questions, stack_outputs

from team_docs import index, search
from team_docs.embed import Embedder

TOP_K = 5
METHODS = ("keyword", "vector", "hybrid", "hybrid, no prefix")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stack", default="team-docs", help="CloudFormation stack that holds the bucket and table")
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    outputs = stack_outputs(session, args.stack)
    embedder = Embedder(session.client("bedrock-runtime"))
    work = Path(tempfile.mkdtemp(prefix="retrieval-"))
    try:
        current = download_index(session, outputs["BucketName"], outputs["TableName"], work / "current")
        plain = without_prefix(work / "current", work / "plain", embedder)
        answerable = [q for q in questions() if q["pages"]]
        rows = [evaluate(q, current, plain, embedder) for q in answerable]
    finally:
        shutil.rmtree(work, ignore_errors=True)

    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "index": {"build": current.build, "pages": current.pages, "chunks": current.chunks},
        "top_k": TOP_K,
        "embedding_tokens": embedder.tokens,
        "summary": summarize(rows),
        "questions": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "retrieval.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (RESULTS / "retrieval.md").write_text(markdown(report))
    print(markdown(report))


def without_prefix(source: Path, directory: Path, embedder: Embedder) -> index.Index:
    """The same chunks, indexed and embedded without the page title and section heading."""
    shutil.copytree(source, directory)
    db = sqlite3.connect(directory / index.DB_FILE)
    try:
        texts = [text for _, text in db.execute("SELECT id, text FROM chunks ORDER BY id")]
        db.execute("DELETE FROM chunks_fts")
        db.execute("INSERT INTO chunks_fts (rowid, title, heading, text) SELECT id, '', '', text FROM chunks")
        db.commit()
    finally:
        db.close()
    np.save(directory / index.VECTOR_FILE, embedder.many(texts))
    return index.load(directory)


def evaluate(question: dict[str, Any], current: index.Index, plain: index.Index, embedder: Embedder) -> dict[str, Any]:
    vector = embedder.one(question["question"])
    expected = set(question["pages"])
    ranks: dict[str, int | None] = {}
    top: dict[str, list[str]] = {}
    for method in METHODS:
        target, name = (plain, "hybrid") if method == "hybrid, no prefix" else (current, method)
        results = search.search(target, question["question"], method=name, top_k=TOP_K, embed=lambda _: vector)
        titles = [result["title"] for result in results]
        ranks[method] = next((rank for rank, title in enumerate(titles, 1) if title in expected), None)
        top[method] = titles
    return {key: question[key] for key in ("id", "by", "kind", "question", "pages")} | {"rank": ranks, "top": top}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups[f"kind: {row['kind']}"].append(row)
        groups[f"by: {row['by']}"].append(row)
    summary = {}
    for group, members in groups.items():
        summary[group] = {"questions": len(members)}
        for method in METHODS:
            found = [row["rank"][method] for row in members]
            summary[group][method] = {
                "hit@5": sum(rank is not None for rank in found) / len(found),
                "mrr": sum(1 / rank for rank in found if rank) / len(found),
            }
    return summary


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Retrieval evaluation, {report['run_at'][:10]}",
        "",
        f"Index build `{report['index']['build']}`: {report['index']['pages']} pages, "
        f"{report['index']['chunks']} sections. Top {report['top_k']} sections per question. "
        f"Questions the docs do not answer are left out.",
        "",
        "| Questions | n | " + " | ".join(f"{m} hit@5 / MRR" for m in METHODS) + " |",
        "|---|---|" + "---|" * len(METHODS),
    ]
    for group, values in report["summary"].items():
        cells = [f"{values[m]['hit@5']:.0%} / {values[m]['mrr']:.2f}" for m in METHODS]
        lines.append(f"| {group} | {values['questions']} | " + " | ".join(cells) + " |")
    lines += ["", "Rank of the first right section, per question (- means not in the top 5):", ""]
    lines.append("| id | by | kind | " + " | ".join(METHODS) + " | question |")
    lines.append("|---|---|---|" + "---|" * len(METHODS) + "---|")
    for row in report["questions"]:
        cells = [str(row["rank"][m] or "-") for m in METHODS]
        lines.append(f"| {row['id']} | {row['by']} | {row['kind']} | " + " | ".join(cells) + f" | {row['question']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
