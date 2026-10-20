"""In-memory stand-ins for Confluence, the DynamoDB and S3 store, and Titan."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from team_docs.confluence import PageList
from team_docs.embed import DIMENSIONS
from team_docs.index import DB_FILE, VECTOR_FILE, Index, load
from team_docs.sync import Sync

FIXTURES = Path(__file__).parent / "fixtures" / "storage"
BASE = "https://example.atlassian.net/wiki"
SPACE_ID = "100"


def page(page_id: str, title: str, body: str, version: int = 1, status: str = "current") -> dict[str, Any]:
    """A page as the v2 API returns it in a list with body-format=storage."""
    return {
        "id": page_id,
        "title": title,
        "status": status,
        "spaceId": SPACE_ID,
        "version": {"number": version, "createdAt": f"2026-10-19T0{version}:00:00.000Z"},
        "body": {"storage": {"value": body}},
        "_links": {"webui": f"/spaces/INV/pages/{page_id}/{title.replace(' ', '+')}"},
    }


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


class FakeConfluence:
    def __init__(self, pages: list[dict[str, Any]]):
        self.listed = {item["id"]: item for item in pages}  # current pages of the space
        self.elsewhere: dict[str, dict[str, Any]] = {}  # trashed, archived or moved pages, by id
        self.checked: list[str] = []

    def space(self, key: str) -> dict[str, Any]:
        return {"id": SPACE_ID, "key": key}

    def current_pages(self, space_id: str) -> PageList:
        return PageList(BASE, list(self.listed.values()))

    def page_status(self, page_id: str) -> tuple[int, dict[str, Any] | None]:
        self.checked.append(page_id)
        found = self.listed.get(page_id) or self.elsewhere.get(page_id)
        return (200, found) if found else (404, None)


class FakeStore:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.state_item: dict[str, Any] = {}
        self.objects: dict[str, bytes] = {}
        self.tags: dict[str, str] = {}
        self.lock: tuple[str, int] | None = None

    def acquire_lock(self, owner: str, now: int, seconds: int) -> bool:
        if self.lock is not None and self.lock[1] >= now:
            return False
        self.lock = (owner, now + seconds)
        return True

    def release_lock(self, owner: str) -> None:
        if self.lock is not None and self.lock[0] == owner:
            self.lock = None

    def pages(self) -> dict[str, dict[str, Any]]:
        return {page_id: dict(item) for page_id, item in self.items.items()}

    def put_page(self, item: dict[str, Any]) -> None:
        _check_storable(item)
        self.items[item["page_id"]] = dict(item)

    def delete_page(self, page_id: str) -> None:
        self.items.pop(page_id, None)

    def state(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.state_item))

    def put_state(self, state: dict[str, Any]) -> None:
        _check_storable(state)
        self.state_item = json.loads(json.dumps(state))

    def put(self, key: str, body: bytes, content_type: str = "") -> None:
        self.objects[key] = body
        self.tags.pop(key, None)  # as in S3, a new object under the same key starts without tags

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def upload(self, path: Path, key: str) -> None:
        self.objects[key] = Path(path).read_bytes()

    def download(self, key: str, path: Path) -> None:
        Path(path).write_bytes(self.objects[key])

    def mark_superseded(self, keys: list[str]) -> None:
        for key in keys:
            self.tags[key] = "superseded"


class FakeEmbedder:
    """The same text always gets the same unit vector. Counts one token per word."""

    def __init__(self) -> None:
        self.tokens = 0
        self.embedded: list[str] = []

    def one(self, text: str) -> np.ndarray:
        self.tokens += len(text.split())
        self.embedded.append(text)
        return unit_vector(text)

    def many(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIMENSIONS), dtype=np.float32)
        return np.vstack([self.one(text) for text in texts])


def unit_vector(text: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    vector = np.random.default_rng(seed).standard_normal(DIMENSIONS).astype(np.float32)
    return vector / np.linalg.norm(vector)


def _check_storable(value: Any) -> None:
    """DynamoDB takes no floats and no numpy types; catch them before they reach AWS."""
    if isinstance(value, dict):
        for item in value.values():
            _check_storable(item)
    elif isinstance(value, list):
        for item in value:
            _check_storable(item)
    elif value is not None and not isinstance(value, (str, int, bool)):
        raise TypeError(f"DynamoDB cannot store {type(value).__name__}: {value!r}")


DEMO_PAGES = [
    ("1", "Start here", "start-here"),
    ("2", "ADR-002 Keep stock out of item responses", "adr-002-no-stock-in-responses"),
    ("3", "ADR-006 Cursor pagination for the item list", "adr-006-list-pagination"),
    ("4", "Decisions", "decisions-index"),
    ("5", "Deploy to dev", "deploy-to-dev"),
    ("6", "Error codes", "error-codes"),
]


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class World:
    """Six demo pages in a fake Confluence, an empty store, and a way to run the real sync on them."""

    def __init__(self, cap: int = 1_000_000):
        self.confluence = FakeConfluence([page(pid, title, fixture(name)) for pid, title, name in DEMO_PAGES])
        self.store = FakeStore()
        self.clock = Clock(datetime(2026, 10, 19, 5, 0, tzinfo=UTC))
        self.cap = cap

    def run(self, force: bool = False) -> tuple[dict[str, Any], FakeEmbedder]:
        embedder = FakeEmbedder()
        sync = Sync(
            self.confluence,  # type: ignore[arg-type]
            self.store,  # type: ignore[arg-type]
            embedder,  # type: ignore[arg-type]
            space_key="INV",
            embedding_cap=self.cap,
            token_expires="2027-01-17",
            clock=self.clock,
        )
        return sync.run(force=force), embedder

    def index(self, directory: Path) -> Index:
        """The current index, as the search function would download it."""
        build = self.store.state_item["current_index"]
        for name in (DB_FILE, VECTOR_FILE):
            self.store.download(f"index/{build}/{name}", directory / name)
        return load(directory)
