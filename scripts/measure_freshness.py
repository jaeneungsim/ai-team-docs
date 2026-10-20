#!/usr/bin/env python3
"""Measure how long an edit in Confluence takes to show up in the search tool.

Each run writes a new marker into the page "Freshness probe" with the write token, then asks the
search function for that marker every 15 seconds, the way the MCP server does, until the result
shows the new version. Before each edit it waits a random 0 to 10 minutes, so edits land at any
point of the 10-minute sync cycle, as real edits do. (Editing straight after the previous run
showed up would always land just after a sync, and measure only the worst case.)

It records three times:

    edited     when Confluence saved the version (version.createdAt)
    synced     when the sync put that version in the index (the result's synced_at)
    visible    when the search first returned it

Each run is saved to evals/results/freshness-<label>.jsonl as soon as it ends, and the summary
to freshness-<label>.json. The probe page is created under the space homepage on the first run
and left in place; send it to the trash when the measurement is done. The cloud id and the email
are not in the repo.

    AWS_PROFILE=team-docs-search .venv/bin/python scripts/measure_freshness.py \\
        --cloud-id "$CONFLUENCE_CLOUD_ID" --email "$CONFLUENCE_EMAIL" --runs 10
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3

from upload_demo_docs import Confluence, keychain_token

TITLE = "Freshness probe"
RESULTS = Path(__file__).resolve().parent.parent / "evals" / "results"
POLL_SECONDS = 15
GIVE_UP_SECONDS = 25 * 60  # two sync cycles and then some


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud-id", default=os.environ.get("CONFLUENCE_CLOUD_ID"))
    parser.add_argument("--email", default=os.environ.get("CONFLUENCE_EMAIL"))
    parser.add_argument("--space", default="INV")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--function", default="team-docs-search")
    parser.add_argument("--wait-max", type=int, default=600, help="seconds; each edit waits a random 0 to this")
    parser.add_argument("--label", default="random", help="name of the result files")
    args = parser.parse_args()
    if not args.cloud_id or not args.email:
        parser.error("--cloud-id and --email (or CONFLUENCE_CLOUD_ID and CONFLUENCE_EMAIL) are required")

    confluence = Confluence(args.cloud_id, args.email, keychain_token())
    space = confluence.space(args.space)
    lambda_client = boto3.Session(region_name="ap-southeast-2").client("lambda")
    RESULTS.mkdir(exist_ok=True)
    progress = RESULTS / f"freshness-{args.label}.jsonl"
    runs = []
    for number in range(1, args.runs + 1):
        waited = random.uniform(0, args.wait_max)
        print(f"run {number}: waiting {waited:.0f} s before the edit", flush=True)
        time.sleep(waited)
        marker = f"freshness-{number}-{secrets.token_hex(4)}"
        page = write_probe(confluence, space, marker)
        edited = datetime.fromisoformat(page["version"]["createdAt"])
        print(f"run {number}: wrote version {page['version']['number']} at {edited:%H:%M:%S}", flush=True)
        found = wait_for(lambda_client, args.function, marker, page["version"]["number"])
        if found is None:
            print(f"run {number}: not visible after {GIVE_UP_SECONDS // 60} minutes", flush=True)
            runs.append({"run": number, "waited_s": round(waited), "edited": edited.isoformat(), "visible": None})
            save(progress, runs[-1])
            continue
        synced, visible = datetime.fromisoformat(found["synced_at"]), found["visible"]
        runs.append(
            {
                "run": number,
                "waited_s": round(waited),
                "version": page["version"]["number"],
                "edited": edited.isoformat(),
                "synced": synced.isoformat(),
                "visible": visible.isoformat(),
                "to_index_s": round((synced - edited).total_seconds()),
                "to_visible_s": round((visible - edited).total_seconds()),
            }
        )
        save(progress, runs[-1])
        print(f"run {number}: indexed after {runs[-1]['to_index_s']} s, visible after {runs[-1]['to_visible_s']} s")
    report(runs, RESULTS / f"freshness-{args.label}.json")


def write_probe(confluence: Confluence, space: dict[str, Any], marker: str) -> dict[str, Any]:
    body = (
        "<p>This page measures how fast an edit reaches the search index. Send it to the trash when the "
        f"measurement is done.</p><p>Run marker: <code>{marker}</code></p>"
    )
    existing = [p for p in confluence.pages(space["id"]) if p["title"] == TITLE and p.get("status") == "current"]
    if not existing:
        return confluence.call(
            "POST",
            "/wiki/api/v2/pages",
            {
                "spaceId": space["id"],
                "status": "current",
                "title": TITLE,
                "parentId": space["homepageId"],
                "body": {"representation": "storage", "value": body},
            },
        )
    page = existing[0]
    return confluence.call(
        "PUT",
        f"/wiki/api/v2/pages/{page['id']}",
        {
            "id": page["id"],
            "status": "current",
            "title": TITLE,
            "body": {"representation": "storage", "value": body},
            "version": {"number": page["version"]["number"] + 1, "message": "Freshness measurement"},
        },
    )


def wait_for(lambda_client: Any, function: str, marker: str, version: int) -> dict[str, Any] | None:
    """Ask the search function for the marker until the probe page comes back at `version`."""
    started = time.monotonic()
    while time.monotonic() - started < GIVE_UP_SECONDS:
        answer = lambda_client.invoke(
            FunctionName=function, Payload=json.dumps({"query": marker, "top_k": 3, "method": "keyword"}).encode()
        )
        result = json.loads(answer["Payload"].read())
        for item in result.get("results", []):
            if item["title"] == TITLE and item["version"] == version and marker in item["text"]:
                return {"synced_at": item["synced_at"], "visible": datetime.now(UTC)}
        time.sleep(POLL_SECONDS)
    return None


def save(progress: Path, run: dict[str, Any]) -> None:
    with progress.open("a") as saved:
        saved.write(json.dumps(run) + "\n")


def report(runs: list[dict[str, Any]], path: Path) -> None:
    done = [run for run in runs if run.get("visible")]
    summary: dict[str, Any] = {"runs": len(runs), "visible": len(done)}
    for key in ("to_index_s", "to_visible_s"):
        values = [run[key] for run in done]
        if values:
            summary[key] = {"median": statistics.median(values), "max": max(values), "min": min(values)}
    path.write_text(json.dumps({"summary": summary, "runs": runs}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
