"""Lambda entry points: the scheduled sync and the search behind the MCP tool."""

from __future__ import annotations

import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import aws
from . import search as ranking
from .confluence import Confluence
from .embed import Embedder
from .env import required
from .index import DB_FILE, VECTOR_FILE, Index, load
from .store import Store
from .sync import Sync

log = logging.getLogger("team_docs")
log.setLevel(logging.INFO)

INDEX_DIR = Path("/tmp/index")
MAX_QUESTION_CHARS = 1000
_loaded: dict[str, Index] = {}  # the index this container has open, kept between invocations


def sync(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Run by the schedule every 10 minutes. `{"force": true}` releases removals that were held back."""
    ssm = aws.client("ssm")
    token = ssm.get_parameter(Name=required("TOKEN_PARAM"), WithDecryption=True)["Parameter"]["Value"]
    run = Sync(
        Confluence(required("CONFLUENCE_CLOUD_ID"), required("CONFLUENCE_EMAIL"), token),
        Store.from_env(),
        Embedder(aws.client("bedrock-runtime")),
        space_key=required("SPACE_KEY"),
        embedding_cap=int(required("EMBED_MONTHLY_TOKENS")),
        token_expires=_parameter(ssm, required("TOKEN_EXPIRES_PARAM")),
    )
    result = run.run(force=bool((event or {}).get("force")))
    log.info("sync", extra={"result": result})
    return result


def search(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """`{"query": "...", "top_k": 5, "method": "hybrid"}`: chunks with their sources, the index, warnings."""
    started = time.monotonic()
    question, method, top_k = _request(event or {})
    store = Store.from_env()
    state = store.state()
    notes = ranking.warnings(state, datetime.now(UTC))
    build = state.get("current_index")
    if not build:
        return {"results": [], "index": {}, "warnings": notes}
    index = _index(store, build)
    embed = Embedder(aws.client("bedrock-runtime")).one if method != "keyword" else None
    results = ranking.search(index, question, method=method, top_k=top_k, embed=embed)
    log.info(
        "search",
        extra={
            "query": question,
            "method": method,
            "top_k": top_k,
            "results": [f"{r['page_id']}#{r['chunk_id']}" for r in results],
            "ms": int((time.monotonic() - started) * 1000),
        },
    )
    return {
        "results": results,
        "index": {
            "build": build,
            "pages": index.pages,
            "chunks": index.chunks,
            "last_success_at": state.get("last_success_at"),
        },
        "warnings": notes,
    }


def _request(event: dict[str, Any]) -> tuple[str, str, int]:
    question = str(event.get("query") or "").strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"query must be 1 to {MAX_QUESTION_CHARS} characters")
    method = str(event.get("method") or "hybrid")
    if method not in ranking.METHODS:
        raise ValueError(f"method must be one of {', '.join(ranking.METHODS)}")
    top_k = event.get("top_k", 5)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= ranking.MAX_TOP_K:
        raise ValueError(f"top_k must be a whole number from 1 to {ranking.MAX_TOP_K}")
    return question, method, top_k


def _index(store: Store, build: str) -> Index:
    """The current index, downloaded once per container and again only when the sync made a new one."""
    loaded = _loaded.get("index")
    if loaded is not None and loaded.build == build:
        return loaded
    directory = INDEX_DIR / build
    if not directory.exists():
        partial = INDEX_DIR / f"{build}.partial"
        partial.mkdir(parents=True, exist_ok=True)
        for name in (DB_FILE, VECTOR_FILE):
            store.download(f"index/{build}/{name}", partial / name)
        partial.rename(directory)
    if loaded is not None:
        loaded.db.close()
        shutil.rmtree(INDEX_DIR / loaded.build, ignore_errors=True)
    _loaded["index"] = load(directory)
    return _loaded["index"]


def _parameter(ssm: Any, name: str) -> str | None:
    try:
        return ssm.get_parameter(Name=name)["Parameter"]["Value"]
    except Exception as err:
        if aws.error_code(err) == "ParameterNotFound":
            return None
        raise
