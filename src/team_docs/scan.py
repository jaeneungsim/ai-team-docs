"""Safety checks on incoming pages.

Wiki text is data. What people cannot see is removed, because an agent should not read what a
reviewer of the page never saw. Text that looks aimed at an AI is kept and flagged: people can
see it, and dropping a page that was flagged by mistake would leave the agent working with
missing information. These checks lower the risk of prompt injection through a page; they do
not remove it, which is why the search tool can only read.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment, Tag

# Matched against a style attribute with its spaces removed and in lower case.
HIDDEN_STYLE = re.compile(
    r"(?:^|;)(?:display:none|visibility:(?:hidden|collapse)"
    r"|font-size:0(?:\.0+)?(?:px|pt|em|rem|%)?|opacity:0(?:\.0+)?"
    r"|color:(?:#fff|#ffffff|white|rgb\(255,255,255\)|rgba\(\d+,\d+,\d+,0(?:\.0+)?\)))(?:;|$)"
)

# Characters that take no space on screen. Ranges, so the source shows no invisible characters.
_INVISIBLE_RANGES = (
    (0x00AD, 0x00AD),  # soft hyphen
    (0x180E, 0x180E),  # Mongolian vowel separator
    (0x200B, 0x200F),  # zero-width space, non-joiner and joiner; left-to-right and right-to-left marks
    (0x202A, 0x202E),  # bidirectional embeddings and overrides
    (0x2060, 0x2064),  # word joiner and invisible operators
    (0x2066, 0x2069),  # bidirectional isolates
    (0xFEFF, 0xFEFF),  # zero-width no-break space
    (0xE0000, 0xE007F),  # tag characters, which can spell out a hidden message
    (0xE0100, 0xE01EF),  # variation selectors supplement, which can also carry hidden data
)
INVISIBLE = re.compile("[" + "".join(f"{re.escape(chr(a))}-{re.escape(chr(b))}" for a, b in _INVISIBLE_RANGES) + "]")

# Text that addresses an AI instead of a person. Adapted from the pr-triage tripwire, without its
# "AI review ... approve" pattern: team docs about an AI review process say that in plain prose.
INSTRUCTION_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+|your\s+)?(?:previous|prior|above|earlier|other)\s+"
        r"(?:instructions|rules|prompts?|guidelines)",
        r"\b(?:disregard|forget|override)\s+(?:all\s+|any\s+)?(?:the\s+|your\s+)?"
        r"(?:previous\s+|prior\s+|above\s+|earlier\s+|existing\s+)?(?:instructions|rules|prompts?|guidelines)\b",
        r"\byou\s+are\s+now\b",
        r"\b(?:system|developer)\s+prompt\b",
        r"\b(?:new|updated|real)\s+instructions?\s*:",
        r"\b(?:note|message|instructions?)\s+(?:to|for)\s+(?:the\s+|any\s+|all\s+)?(?:ai|llm|assistant|agent|model)s?\b",
        r"\b(?:ai|llm)\s+(?:coding\s+)?(?:agent|assistant|model|reviewer)s?\s*:",
        r"\b(?:do\s+not|don't|never)\s+(?:tell|inform|show)\s+the\s+user\b",
    )
)
MAX_QUOTES = 3


def strip_hidden(soup: BeautifulSoup) -> int:
    """Remove HTML comments and elements styled to be invisible. Returns how many characters went."""
    removed = 0
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        removed += len(comment)
        comment.extract()
    while (tag := soup.find(_is_hidden)) is not None:
        removed += len(tag.get_text())
        tag.decompose()
    return removed


def strip_invisible(text: str) -> tuple[str, int]:
    """Text without zero-width, bidirectional control and tag characters, and how many there were."""
    return INVISIBLE.subn("", text)


def flag_instructions(text: str) -> list[str]:
    """Short quotes of text that looks aimed at an AI agent."""
    quotes: list[str] = []
    for pattern in INSTRUCTION_PATTERNS:
        if match := pattern.search(text):
            end = match.end()
            while end < len(text) and text[end].isalnum():  # finish the last word
                end += 1
            quote = " ".join(text[match.start() : end].split())[:80]
            if quote not in quotes:
                quotes.append(quote)
        if len(quotes) == MAX_QUOTES:
            break
    return quotes


def _is_hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden"):
        return True
    style = "".join(str(tag.get("style", "")).split()).lower()
    return bool(style) and HIDDEN_STYLE.search(style) is not None
