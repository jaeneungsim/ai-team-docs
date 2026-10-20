#!/usr/bin/env python3
"""Upload demo-docs/ to the demo Confluence space with the write token.

Pages are matched by title. A missing page is created under its parent, and a page whose converted
body changed since the last upload is updated with the next version number. The doc marked
`home: true` replaces the space homepage. Pages that have no file here are left alone.

The token comes from the macOS keychain (service team-docs-confluence-write) and is never printed.
The cloud id and the account email are not in the repo; pass them as flags or environment variables.

    .venv/bin/python scripts/upload_demo_docs.py --cloud-id "$CONFLUENCE_CLOUD_ID" \\
        --email "$CONFLUENCE_EMAIL" --space INV --dry-run
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from demo_docs import DOCS_DIR, STAGES, load_docs
from md_to_storage import convert

KEYCHAIN_SERVICE = "team-docs-confluence-write"
STATE_FILE = DOCS_DIR / ".upload-state.json"


class Confluence:
    """The few v2 REST calls the upload needs, through the api.atlassian.com gateway."""

    def __init__(self, cloud_id: str, email: str, token: str):
        self.root = f"https://api.atlassian.com/ex/confluence/{cloud_id}"
        self._auth = "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(5):
            request = urllib.request.Request(
                self.root + path,
                data=data,
                method=method,
                headers={"Authorization": self._auth, "Accept": "application/json", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as err:
                # A POST that failed with 5xx may still have created the page, so only 429 is retried for it.
                retry = err.code == 429 or (err.code >= 500 and method != "POST")
                if retry and attempt < 4:
                    time.sleep(float(err.headers.get("Retry-After") or 2**attempt))
                    continue
                detail = err.read().decode("utf-8", "replace")[:500]
                raise SystemExit(f"{method} {path.split('?')[0]} failed: HTTP {err.code} {detail}") from None
        raise AssertionError("unreachable")

    def space(self, key: str) -> dict[str, Any]:
        results = self.call("GET", f"/wiki/api/v2/spaces?keys={urllib.parse.quote(key)}")["results"]
        if not results:
            raise SystemExit(f"space {key} not found, or the token cannot see it")
        return results[0]

    def pages(self, space_id: str) -> list[dict[str, Any]]:
        pages, path = [], f"/wiki/api/v2/spaces/{space_id}/pages?limit=250"
        while path:
            answer = self.call("GET", path)
            pages.extend(answer["results"])
            path = answer.get("_links", {}).get("next")
        return pages


def keychain_token() -> str:
    found = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", os.environ["USER"], "-w"],
        capture_output=True,
        text=True,
    )
    if found.returncode != 0:
        raise SystemExit(f"no keychain item {KEYCHAIN_SERVICE} for {os.environ['USER']}")
    return found.stdout.strip()


def digest(storage: str) -> str:
    return hashlib.sha256(storage.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud-id", default=os.environ.get("CONFLUENCE_CLOUD_ID"))
    parser.add_argument("--email", default=os.environ.get("CONFLUENCE_EMAIL"))
    parser.add_argument("--space", default="INV")
    parser.add_argument("--stage", default="v1", choices=STAGES, help="upload docs up to this stage")
    parser.add_argument("--dry-run", action="store_true", help="only print what would change")
    args = parser.parse_args()
    if not args.cloud_id or not args.email:
        parser.error("--cloud-id and --email (or CONFLUENCE_CLOUD_ID and CONFLUENCE_EMAIL) are required")

    docs = load_docs(args.stage)
    confluence = Confluence(args.cloud_id, args.email, keychain_token())
    space = confluence.space(args.space)
    existing = {page["title"]: page for page in confluence.pages(space["id"])}
    by_id = {page["id"]: page for page in existing.values()}
    state: dict[str, dict[str, str]] = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    ids: dict[str, str] = {}
    counts = {"create": 0, "update": 0, "skip": 0}

    for doc in docs:
        storage = convert(doc.body)
        page = by_id.get(space["homepageId"]) if doc.home else existing.get(doc.title)
        if page is not None:
            ids[doc.title] = page["id"]
            if state.get(doc.title, {}).get("hash") == digest(storage):
                counts["skip"] += 1
                continue
        if page is None:
            counts["create"] += 1
            print(f"create  {doc.title}  (under {doc.parent})")
            if args.dry_run:
                ids[doc.title] = f"<new:{doc.title}>"
                continue
            page = confluence.call(
                "POST",
                "/wiki/api/v2/pages",
                {
                    "spaceId": space["id"],
                    "status": "current",
                    "title": doc.title,
                    "parentId": ids[doc.parent],
                    "body": {"representation": "storage", "value": storage},
                },
            )
        else:
            version = page["version"]["number"] + 1
            counts["update"] += 1
            print(f"update  {doc.title}  (version {version})")
            if args.dry_run:
                continue
            page = confluence.call(
                "PUT",
                f"/wiki/api/v2/pages/{page['id']}",
                {
                    "id": page["id"],
                    "status": "current",
                    "title": doc.title,
                    "body": {"representation": "storage", "value": storage},
                    "version": {"number": version, "message": "Updated from demo-docs"},
                },
            )
        ids[doc.title] = page["id"]
        state[doc.title] = {"id": page["id"], "hash": digest(storage)}
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    mode = "dry run: " if args.dry_run else ""
    print(f"{mode}{counts['create']} to create, {counts['update']} to update, {counts['skip']} unchanged")


if __name__ == "__main__":
    main()
