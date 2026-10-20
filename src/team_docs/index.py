"""The search index: one SQLite file and one vector file.

The SQLite file has the pages, their chunks, and an FTS5 table over the chunks for keyword
search. The vector file holds one row per chunk, in chunk id order (row i is chunk i + 1). The
sync builds a new index whenever something changed and uploads it under index/<build>/; the
search function downloads the current build once per container.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .embed import DIMENSIONS

DB_FILE = "index.sqlite"
VECTOR_FILE = "vectors.npy"

SCHEMA = """
CREATE TABLE pages (
    page_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    version INTEGER NOT NULL,
    edited_at TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    hidden_chars INTEGER NOT NULL
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES pages (page_id),
    heading TEXT NOT NULL,
    text TEXT NOT NULL,
    flags TEXT NOT NULL
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(title, heading, text, tokenize = 'porter unicode61');
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass
class IndexPage:
    page_id: str
    title: str
    url: str
    version: int
    edited_at: str
    synced_at: str
    hidden_chars: int
    chunks: list[dict[str, Any]]  # {"heading", "text", "flags"} in page order
    vectors: np.ndarray | None = None  # one row per chunk, or None when the page has no embeddings


@dataclass
class Index:
    build: str
    pages: int
    chunks: int
    db: sqlite3.Connection
    vectors: np.ndarray
    has_vector: np.ndarray = field(init=False)  # False for chunks that were never embedded

    def __post_init__(self) -> None:
        self.has_vector = np.linalg.norm(self.vectors, axis=1) > 0 if len(self.vectors) else np.zeros(0, dtype=bool)


def build(pages: list[IndexPage], directory: Path, build_id: str) -> tuple[Path, Path]:
    """Write the two index files into `directory` and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    db_path, vector_path = directory / DB_FILE, directory / VECTOR_FILE
    db_path.unlink(missing_ok=True)
    rows: list[np.ndarray] = []
    db = sqlite3.connect(db_path)
    try:
        db.executescript(SCHEMA)
        for page in pages:
            db.execute(
                "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (page.page_id, page.title, page.url, page.version, page.edited_at, page.synced_at, page.hidden_chars),
            )
            for position, chunk in enumerate(page.chunks):
                chunk_id = len(rows) + 1
                db.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, page.page_id, chunk["heading"], chunk["text"], json.dumps(chunk["flags"])),
                )
                db.execute(
                    "INSERT INTO chunks_fts (rowid, title, heading, text) VALUES (?, ?, ?, ?)",
                    (chunk_id, page.title, chunk["heading"], chunk["text"]),
                )
                vector = page.vectors[position] if page.vectors is not None else None
                rows.append(vector if vector is not None else np.zeros(DIMENSIONS, dtype=np.float32))
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("build", build_id), ("pages", str(len(pages))), ("chunks", str(len(rows)))],
        )
        db.commit()
    finally:
        db.close()
    np.save(vector_path, np.vstack(rows) if rows else np.zeros((0, DIMENSIONS), dtype=np.float32))
    return db_path, vector_path


def load(directory: Path) -> Index:
    db = sqlite3.connect(f"file:{directory / DB_FILE}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    return Index(meta["build"], int(meta["pages"]), int(meta["chunks"]), db, np.load(directory / VECTOR_FILE))
