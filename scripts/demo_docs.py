"""Load the demo docs in demo-docs/: front matter, page tree and upload order."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "demo-docs"
STAGES = ("v1", "v2", "v3")


@dataclass(frozen=True)
class Doc:
    path: Path
    title: str
    parent: str | None  # None only for the space homepage
    order: int
    stage: str
    body: str

    @property
    def home(self) -> bool:
        return self.parent is None


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """`---` / `key: value` lines / `---`, then the Markdown body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing front matter")
    meta: dict[str, str] = {}
    for number, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "".join(lines[number + 1 :]).lstrip("\n")
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"bad front matter line: {line.strip()!r}")
        meta[key.strip()] = value.strip()
    raise ValueError("front matter is not closed")


def load_docs(stage: str = "v1", root: Path = DOCS_DIR) -> list[Doc]:
    """Docs up to `stage`, parents before children, siblings by `order`."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    docs = []
    for path in sorted(root.rglob("*.md")):
        if path.name == "README.md":
            continue
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        doc_stage = meta.get("stage", "v1")
        if doc_stage not in STAGES:
            raise ValueError(f"{path}: unknown stage {doc_stage}")
        if STAGES.index(doc_stage) > STAGES.index(stage):
            continue
        is_home = meta.get("home") == "true"
        docs.append(
            Doc(
                path=path,
                title=meta["title"],
                parent=None if is_home else meta["parent"],
                order=int(meta.get("order", "0")),
                stage=doc_stage,
                body=body,
            )
        )
    _check_tree(docs)
    by_title = {doc.title: doc for doc in docs}

    def depth(doc: Doc) -> int:
        return 0 if doc.parent is None else 1 + depth(by_title[doc.parent])

    return sorted(docs, key=lambda doc: (depth(doc), doc.parent or "", doc.order, doc.title))


def _check_tree(docs: list[Doc]) -> None:
    titles = [doc.title for doc in docs]
    duplicates = sorted({title for title in titles if titles.count(title) > 1})
    if duplicates:
        raise ValueError(f"duplicate titles: {', '.join(duplicates)}")
    homes = [doc for doc in docs if doc.home]
    if len(homes) != 1:
        raise ValueError(f"exactly one doc needs `home: true`, found {len(homes)}")
    known = set(titles)
    for doc in docs:
        if doc.parent is not None and doc.parent not in known:
            raise ValueError(f"{doc.path.name}: parent {doc.parent!r} is not a doc")
