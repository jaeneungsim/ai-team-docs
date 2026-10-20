"""One sync run: Confluence, read only, into the search index.

1. Take the run lock, so two runs never overlap.
2. List the current pages of the space with their bodies.
3. Process new and changed pages: convert, check, chunk, embed, and keep each step in S3.
   The files of the version a page replaces are tagged superseded, so the bucket deletes them.
4. Remove pages that left the list, after checking each one, and tag their files the same way.
   Hold back if too many left at once.
5. If anything changed, build a new index and make it the current one.
6. Record the run in the STATE item, which the search function reads for its warnings.
"""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from . import chunk, convert, index, scan
from .confluence import Confluence
from .embed import DIMENSIONS, Embedder
from .store import Store

PIPELINE = 1  # raise when conversion or chunking changes; every page is then processed again
LOCK_SECONDS = 6 * 60  # longer than the function's five-minute timeout
HOLD_SHARE = 0.2  # when more of the index than this leaves in one run, removals wait for a person


@dataclass
class Report:
    started_at: str
    finished_at: str = ""
    ok: bool = False
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    held: list[str] = field(default_factory=list)  # titles of pages whose removal is held back
    errors: list[dict[str, str]] = field(default_factory=list)  # pages that could not be processed
    warnings: list[str] = field(default_factory=list)
    embedding_tokens: int = 0
    embedding_capped: bool = False
    build: str = ""  # the index build this run made, if any
    error: str = ""  # why the run failed, if it did


class Sync:
    def __init__(
        self,
        confluence: Confluence,
        store: Store,
        embedder: Embedder,
        *,
        space_key: str,
        embedding_cap: int,
        token_expires: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._confluence = confluence
        self._store = store
        self._embedder = embedder
        self._space_key = space_key
        self._cap = embedding_cap
        self._token_expires = token_expires
        self._clock = clock

    def run(self, force: bool = False) -> dict[str, Any]:
        """`force` removes pages even when more than HOLD_SHARE of the index left at once."""
        now = self._clock()
        owner = uuid.uuid4().hex
        if not self._store.acquire_lock(owner, int(now.timestamp()), LOCK_SECONDS):
            return {"skipped": "another sync run is in progress"}
        state = self._store.state()
        report = Report(started_at=_iso(now))
        try:
            self._sync(state, report, now, force)
            report.ok = True
        except Exception as err:
            report.error = _describe(err)
            raise
        finally:
            try:
                report.finished_at = _iso(self._clock())
                report.embedding_tokens = self._embedder.tokens
                self._record(state, report, now)
            finally:
                self._store.release_lock(owner)
        return asdict(report)

    def _sync(self, state: dict[str, Any], report: Report, now: datetime, force: bool) -> None:
        space = self._confluence.space(self._space_key)
        listing = self._confluence.current_pages(space["id"])
        known = self._store.pages()
        used = _tokens_this_month(state, now)
        changed = False
        for page in listing.pages:
            item = known.get(page["id"])
            can_embed = used + self._embedder.tokens < self._cap
            if not _needs_work(item, page, can_embed):
                report.unchanged += 1
                continue
            try:
                new_item = self._process(page, listing.base, item, can_embed, now)
            except Exception as err:  # one page that cannot be processed must not stop the others
                report.errors.append({"page_id": page["id"], "title": page["title"], "error": _describe(err)})
                continue
            report.embedding_capped |= not can_embed
            self._store.put_page(new_item)
            changed = True
            if item is None:
                report.created += 1
            else:
                report.updated += 1
                # Processing the same version again writes the same keys, so only replaced files are tagged.
                self._store.mark_superseded(sorted(_files(item) - _files(new_item)))
        listed = {page["id"] for page in listing.pages}
        changed |= self._remove_missing(known, listed, str(space["id"]), report, force)
        if changed or not state.get("current_index"):
            report.build = self._build_index(now)

    def _process(
        self, page: dict[str, Any], base: str, previous: dict[str, Any] | None, can_embed: bool, now: datetime
    ) -> dict[str, Any]:
        page_id, title, version = page["id"], page["title"], page["version"]["number"]
        storage = page["body"]["storage"]["value"]
        converted = convert.to_markdown(storage)
        pieces = chunk.split(converted.markdown)
        texts = [chunk.index_text(title, piece) for piece in pieces]
        chunks = [
            {"heading": piece.heading, "text": piece.text, "flags": scan.flag_instructions(text), "hash": _hash(text)}
            for piece, text in zip(pieces, texts, strict=True)
        ]
        vectors = self._vectors(chunks, texts, previous) if can_embed and chunks else None
        name = f"{page_id}/{version}"
        keys = {
            "raw_key": f"raw/{name}.xhtml",
            "md_key": f"md/{name}.md",
            "chunks_key": f"chunks/{name}.json",
            "vectors_key": f"vectors/{name}.npy" if vectors is not None else None,
        }
        self._store.put(keys["raw_key"], storage.encode(), "application/xhtml+xml")
        self._store.put(keys["md_key"], converted.markdown.encode(), "text/markdown; charset=utf-8")
        self._store.put(keys["chunks_key"], json.dumps(chunks, ensure_ascii=False).encode(), "application/json")
        if vectors is not None:
            self._store.put(f"vectors/{name}.npy", _npy(vectors))
        return {
            "page_id": page_id,
            "title": title,
            "version": version,
            "edited_at": page["version"]["createdAt"],
            "url": base + page["_links"]["webui"],
            "synced_at": _iso(now),
            "chunk_count": len(chunks),
            "hidden_chars": converted.hidden_chars,
            "flags": sorted({quote for item in chunks for quote in item["flags"]}),
            "pipeline": PIPELINE,
            **keys,
        }

    def _vectors(self, chunks: list[dict[str, Any]], texts: list[str], previous: dict[str, Any] | None) -> np.ndarray:
        """Embeddings for the chunks. Chunks whose text did not change keep the vectors they had."""
        kept: dict[str, np.ndarray] = {}
        if previous and previous.get("vectors_key"):
            old_chunks = json.loads(self._store.get(previous["chunks_key"]))
            old_vectors = _from_npy(self._store.get(previous["vectors_key"]))
            kept = {old.get("hash", ""): vector for old, vector in zip(old_chunks, old_vectors, strict=True)}
        missing = [position for position, item in enumerate(chunks) if item["hash"] not in kept]
        fresh = self._embedder.many([texts[position] for position in missing])
        rows = [kept.get(item["hash"]) for item in chunks]
        for position, vector in zip(missing, fresh, strict=True):
            rows[position] = vector
        return np.vstack(rows).astype(np.float32)

    def _remove_missing(
        self, known: dict[str, dict[str, Any]], listed: set[str], space_id: str, report: Report, force: bool
    ) -> bool:
        """Check every indexed page that is no longer listed, then remove the ones that are gone."""
        gone: list[str] = []
        for page_id, item in known.items():
            if page_id in listed:
                continue
            status, page = self._confluence.page_status(page_id)
            # A trashed or archived page still answers 200, so the status field decides.
            if status == 200 and page and page.get("status") == "current" and str(page.get("spaceId")) == space_id:
                report.warnings.append(f"{item['title']} is current but was missing from the page list; kept")
                continue
            gone.append(page_id)
        if not gone:
            return False
        if len(gone) > HOLD_SHARE * len(known) and not force:
            report.held = [known[page_id]["title"] for page_id in gone]
            return False
        for page_id in gone:
            # Tag before deleting the item: if the delete fails, the next run finds the page again.
            self._store.mark_superseded(sorted(_files(known[page_id])))
            self._store.delete_page(page_id)
            report.removed += 1
        return True

    def _build_index(self, now: datetime) -> str:
        items = sorted(self._store.pages().values(), key=lambda item: item["title"])
        with ThreadPoolExecutor(max_workers=8) as pool:
            pages = list(pool.map(self._index_page, items))
        build_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
        with tempfile.TemporaryDirectory() as directory:
            db_path, vector_path = index.build(pages, Path(directory), build_id)
            self._store.upload(db_path, f"index/{build_id}/{index.DB_FILE}")
            self._store.upload(vector_path, f"index/{build_id}/{index.VECTOR_FILE}")
        return build_id

    def _index_page(self, item: dict[str, Any]) -> index.IndexPage:
        vectors = _from_npy(self._store.get(item["vectors_key"])) if item.get("vectors_key") else None
        return index.IndexPage(
            page_id=item["page_id"],
            title=item["title"],
            url=item["url"],
            version=item["version"],
            edited_at=item["edited_at"],
            synced_at=item["synced_at"],
            hidden_chars=item["hidden_chars"],
            chunks=json.loads(self._store.get(item["chunks_key"])),
            vectors=vectors,
        )

    def _record(self, state: dict[str, Any], report: Report, now: datetime) -> None:
        new_state = {
            **state,
            "last_run_at": report.started_at,
            "last_run": asdict(report),
            "embedding_month": f"{now:%Y-%m}",
            "embedding_tokens": _tokens_this_month(state, now) + report.embedding_tokens,
            "token_expires": self._token_expires,
        }
        if report.ok:
            new_state["last_success_at"] = report.finished_at
        previous = state.get("current_index")
        if report.build:
            new_state["current_index"] = report.build
        self._store.put_state(new_state)
        if report.build and previous and previous != report.build:
            self._store.mark_superseded([f"index/{previous}/{index.DB_FILE}", f"index/{previous}/{index.VECTOR_FILE}"])


def _needs_work(item: dict[str, Any] | None, page: dict[str, Any], can_embed: bool) -> bool:
    if item is None or item.get("pipeline") != PIPELINE:
        return True
    if item["version"] != page["version"]["number"] or item["title"] != page["title"]:
        return True
    # Pages processed while the monthly embedding limit was reached get their vectors later.
    return can_embed and item.get("chunk_count", 0) > 0 and not item.get("vectors_key")


def _files(item: dict[str, Any]) -> set[str]:
    """The S3 keys of the files one PAGE item points to."""
    return {item[key] for key in ("raw_key", "md_key", "chunks_key", "vectors_key") if item.get(key)}


def _tokens_this_month(state: dict[str, Any], now: datetime) -> int:
    return int(state.get("embedding_tokens", 0)) if state.get("embedding_month") == f"{now:%Y-%m}" else 0


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _npy(vectors: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, vectors.astype(np.float32))
    return buffer.getvalue()


def _from_npy(data: bytes) -> np.ndarray:
    vectors = np.load(io.BytesIO(data))
    return vectors.reshape(-1, DIMENSIONS)


def _describe(err: Exception) -> str:
    return f"{type(err).__name__}: {err}"[:500]


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")
