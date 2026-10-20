#!/usr/bin/env python3
"""The edit for the comparison scene, made with the write token: the team stops re-running old deploys.

Step 2 of the rollback runbook, the fast path (re-run the last good deploy-dev run), becomes the
new rule: do not re-run old deploys, revert in a PR. An agent that reads an old copy of the
runbook still suggests the re-run; one that searches the synced space gets the new rule, with the
page version and edit time. `--restore` puts the page back to its text in demo-docs/, so the
space matches the repo again. The cloud id and the account email are not in the repo.

    .venv/bin/python scripts/edit_for_scene.py --cloud-id "$CONFLUENCE_CLOUD_ID" \\
        --email "$CONFLUENCE_EMAIL" [--restore]
"""

from __future__ import annotations

import argparse
import os

from demo_docs import load_docs
from md_to_storage import convert
from upload_demo_docs import Confluence, keychain_token

TITLE = "Roll back a bad deploy on dev"
NEW_RULE = (
    "## 2. Do not re-run old deploys\n\n"
    "Re-running an old `deploy-dev` run used to be the fast path. The team stopped on 2026-10-20: the "
    "redeployed commit only lasts until the next merge, which deploys the bad commit again. Go straight to "
    "step 3. The revert PR is the only way back.\n\n"
    "::: warning\n"
    "If `dev` must work before the revert PR is merged, ask in the team channel. Do not re-run old "
    "`deploy-dev` runs.\n"
    ":::\n\n"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud-id", default=os.environ.get("CONFLUENCE_CLOUD_ID"))
    parser.add_argument("--email", default=os.environ.get("CONFLUENCE_EMAIL"))
    parser.add_argument("--space", default="INV")
    parser.add_argument("--restore", action="store_true", help="put back the text in demo-docs/")
    args = parser.parse_args()
    if not args.cloud_id or not args.email:
        parser.error("--cloud-id and --email (or CONFLUENCE_CLOUD_ID and CONFLUENCE_EMAIL) are required")

    body = next(doc.body for doc in load_docs() if doc.title == TITLE)
    if not args.restore:
        start, end = body.find("## 2. Fast path"), body.find("## 3. ")
        if start < 0 or end < start:
            raise SystemExit("the runbook in demo-docs/ no longer has the fast path this edit replaces")
        body = body[:start] + NEW_RULE + body[end:]
    confluence = Confluence(args.cloud_id, args.email, keychain_token())
    space = confluence.space(args.space)
    page = next(p for p in confluence.pages(space["id"]) if p["title"] == TITLE and p.get("status") == "current")
    version = page["version"]["number"] + 1
    message = "Restore the fast path (comparison scene done)" if args.restore else "Stop re-running old deploys"
    updated = confluence.call(
        "PUT",
        f"/wiki/api/v2/pages/{page['id']}",
        {
            "id": page["id"],
            "status": "current",
            "title": TITLE,
            "body": {"representation": "storage", "value": convert(body)},
            "version": {"number": version, "message": message},
        },
    )
    print(f"{TITLE}: version {updated['version']['number']} at {updated['version']['createdAt']}")


if __name__ == "__main__":
    main()
