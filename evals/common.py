"""What the evaluation scripts share: the questions, the deployed stack, and answer matching."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "questions.yaml"
RESULTS = ROOT / "evals" / "results"
SITE = re.compile(r"https://[a-z0-9-]+\.atlassian\.net")
for path in (ROOT / "src", ROOT / "mcp"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def questions() -> list[dict[str, Any]]:
    import yaml

    return yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))


def mentions(text: str, fact: str) -> bool:
    """Whole-word match without case: "ui" does not match "guide", "INV-" matches "INV-123"."""
    left = r"(?<!\w)" if fact[0].isalnum() else ""
    right = r"(?!\w)" if fact[-1].isalnum() else ""
    return re.search(left + re.escape(fact) + right, text, re.I) is not None


def has_fact(text: str, fact: str | list[str]) -> bool:
    """A fact is a string, or a list of strings of which one is enough."""
    options = fact if isinstance(fact, list) else [fact]
    return any(mentions(text, str(option)) for option in options)


def mask_site(text: str) -> str:
    """Results go into the repo, the site address does not: answers that cite a page link lose the site."""
    return SITE.sub("https://<site>.atlassian.net", text)


def stack_outputs(session: Any, stack: str) -> dict[str, str]:
    described = session.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]
    return {output["OutputKey"]: output["OutputValue"] for output in described.get("Outputs", [])}


def download_index(session: Any, bucket: str, table: str, directory: Path) -> Any:
    """The index the search function is using now, so the evaluation ranks exactly what the tool ranks."""
    from team_docs import index

    state = session.resource("dynamodb").Table(table).get_item(Key={"pk": "STATE", "sk": "STATE"})["Item"]
    directory.mkdir(parents=True)
    s3 = session.client("s3")
    for name in (index.DB_FILE, index.VECTOR_FILE):
        s3.download_file(bucket, f"index/{state['current_index']}/{name}", str(directory / name))
    return index.load(directory)
