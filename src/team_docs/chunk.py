"""Split a page's Markdown into sections that search can return on their own.

A chunk is one section under an h1, h2 or h3 heading. Sections shorter than MIN_CHARS join the
next section, and sections longer than MAX_CHARS are split between paragraphs. Each chunk is
indexed and embedded with "page title > section heading" in front, so a section such as
"Steps" still says which page it belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 3000
MIN_CHARS = 300
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Chunk:
    heading: str  # the first section's heading, or "" for text before the first heading
    text: str  # Markdown without that heading line; later sections keep theirs


def split(markdown: str) -> list[Chunk]:
    sections = _merge_short(_sections(markdown))
    return [Chunk(heading, part) for heading, text in sections for part in _split_long(text)]


def index_text(title: str, chunk: Chunk) -> str:
    """What gets indexed and embedded: the page and section names, then the text."""
    prefix = f"{title} > {chunk.heading}" if chunk.heading else title
    return f"{prefix}\n\n{chunk.text}"


def _sections(markdown: str) -> list[tuple[str, str, str]]:
    """(heading, heading line, body) for each h1-h3 section, ignoring `#` lines inside code."""
    sections: list[tuple[str, str, list[str]]] = [("", "", [])]
    in_code = False
    for line in markdown.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        match = None if in_code else HEADING.match(line)
        if match:
            sections.append((match[2], line, []))
        else:
            sections[-1][2].append(line)
    found = [(heading, line, "\n".join(body).strip()) for heading, line, body in sections]
    return [section for section in found if section[0] or section[2]]


def _merge_short(sections: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """(heading, text) pairs. Short sections are joined with the ones after them; a short last
    group goes into the chunk before it."""
    merged: list[tuple[str, str]] = []
    group: list[tuple[str, str, str]] = []
    for section in sections:
        group.append(section)
        if len(_join(group)) >= MIN_CHARS:
            merged.append((group[0][0], _join(group)))
            group = []
    if group and merged:
        heading, text = merged.pop()
        merged.append((heading, f"{text}\n\n{_join(group, first_heading=True)}"))
    elif group:
        merged.append((group[0][0], _join(group)))
    return merged


def _join(group: list[tuple[str, str, str]], first_heading: bool = False) -> str:
    """The group's Markdown. The first heading line is left out unless asked for: the chunk's
    heading already names it."""
    parts: list[str] = []
    for position, (_, line, body) in enumerate(group):
        if position or first_heading:
            parts.append(line)
        parts.append(body)
    return "\n\n".join(part for part in parts if part)


def _split_long(text: str) -> list[str]:
    """Pieces of at most MAX_CHARS, cut between paragraphs and never inside a code block."""
    if len(text) <= MAX_CHARS:
        return [text]
    pieces: list[str] = []
    current = ""
    for block in _blocks(text):
        while len(block) > MAX_CHARS:  # one block bigger than a chunk: cut it at a line break
            cut = block.rfind("\n", 0, MAX_CHARS)
            cut = cut if cut > 0 else MAX_CHARS
            if current:
                pieces.append(current)
                current = ""
            pieces.append(block[:cut].rstrip())
            block = block[cut:].lstrip("\n")
        if current and len(current) + 2 + len(block) > MAX_CHARS:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{block}" if current else block
    if current:
        pieces.append(current)
    return pieces


def _blocks(text: str) -> list[str]:
    """Paragraphs, lists, tables and whole code blocks, in order."""
    blocks: list[str] = []
    current: list[str] = []
    in_code = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        if not line.strip() and not in_code:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks
