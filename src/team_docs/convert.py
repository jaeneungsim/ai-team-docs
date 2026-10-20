"""Confluence storage format to Markdown.

Storage format is XHTML with Confluence elements (`ac:` macros and `ri:` resource identifiers),
and it uses HTML entities such as `&nbsp;`, so it is parsed as HTML, not XML. Conversion has two
steps: Confluence elements are rewritten into plain HTML, then markdownify writes the Markdown.
Anything this module does not know keeps the text a reader would see; nothing is dropped quietly
except what is listed in DROPPED_MACROS and edit-only hints.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter

from . import scan

PANELS = {"info": "Info", "note": "Note", "warning": "Warning", "tip": "Tip", "panel": "Panel"}
CODE_MACROS = {"code", "noformat"}
# Navigation and generated lists: they repeat other pages or carry no text of their own.
DROPPED_MACROS = {"toc", "children", "pagetree", "recently-updated", "contentbylabel", "anchor", "attachments"}
# `📘` written out as text, which some emoji fallbacks are.
ESCAPED_UTF16 = re.compile("(?:" + re.escape(chr(92)) + "u[0-9a-fA-F]{4})+")


@dataclass(frozen=True)
class Converted:
    markdown: str
    hidden_chars: int  # characters removed because people cannot see them


def to_markdown(storage: str) -> Converted:
    soup = BeautifulSoup(storage, "html.parser")
    hidden = scan.strip_hidden(soup)
    _rewrite(soup, soup)
    markdown = _Markdown(
        heading_style="ATX",
        bullets="-",
        escape_asterisks=False,
        escape_underscores=False,
        escape_misc=False,
        table_infer_header=True,
        code_language_callback=_code_language,
    ).convert_soup(soup)
    markdown, invisible = scan.strip_invisible(markdown)
    return Converted(_tidy(markdown), hidden + invisible)


def _rewrite(soup: BeautifulSoup, node: Tag) -> None:
    """Replace Confluence elements under `node` with plain HTML, parents before children."""
    for child in list(node.children):
        if isinstance(child, Tag):
            replacement = _replace(soup, child)
            if replacement is not None:
                _rewrite(soup, replacement)


def _replace(soup: BeautifulSoup, tag: Tag) -> Tag | None:
    """Rewrite one element. Returns the element whose children still need rewriting, if any."""
    name = tag.name
    if name in ("ac:structured-macro", "ac:macro"):
        return _macro(soup, tag)
    if name == "ac:link":
        tag.replace_with(_link_text(tag))
        return None
    if name == "ac:image":
        tag.replace_with(f"[image: {_image_name(tag)}]")
        return None
    if name == "ac:emoticon":
        tag.replace_with(_emoji(tag))
        return None
    if name == "ac:task-list":
        return _tasks(soup, tag)
    if name == "ac:adf-extension":
        return _adf(soup, tag)
    if name in ("ac:placeholder", "ac:parameter", "ac:adf-attribute") or name.startswith("ri:"):
        tag.decompose()  # edit-only hints, macro settings and resource ids: nothing a reader sees
        return None
    if name == "ac:plain-text-body":
        tag.replace_with(tag.get_text())
        return None
    if name.startswith("ac:"):
        _rewrite(soup, tag)  # unknown Confluence element: keep what is inside
        tag.unwrap()
        return None
    if name == "time" and not tag.get_text(strip=True) and tag.get("datetime"):
        tag.replace_with(str(tag["datetime"]))
        return None
    if name in ("td", "th"):
        _rewrite(soup, tag)
        _flatten_lists(tag)
        return None
    return tag


def _macro(soup: BeautifulSoup, macro: Tag) -> Tag | None:
    name = str(macro.get("ac:name", "")).lower()
    if name in CODE_MACROS:
        macro.replace_with(_code_block(soup, _body(macro, "ac:plain-text-body"), _param(macro, "language")))
        return None
    if name in PANELS:
        title = _param(macro, "title")
        return _wrap(soup, macro, "blockquote", f"{PANELS[name]}: {title}" if title else PANELS[name])
    if name == "expand":
        return _wrap(soup, macro, "div", _param(macro, "title") or "Details")
    if name == "status":
        macro.replace_with(_param(macro, "title"))
        return None
    if name == "jira" and _param(macro, "key"):
        macro.replace_with(_param(macro, "key"))
        return None
    if name in DROPPED_MACROS:
        macro.decompose()
        return None
    # Any other macro, including page properties (details) and layout macros: keep its body.
    if _body(macro, "ac:rich-text-body") is not None:
        return _wrap(soup, macro, "div", None)
    if (plain := _body(macro, "ac:plain-text-body")) is not None:
        macro.replace_with(_code_block(soup, plain, ""))
        return None
    macro.decompose()
    return None


def _param(macro: Tag, name: str) -> str:
    for parameter in macro.find_all("ac:parameter", recursive=False):
        if parameter.get("ac:name") == name:
            return parameter.get_text().strip()
    return ""


def _body(macro: Tag, name: str) -> Tag | None:
    found = macro.find(name, recursive=False)
    return found if isinstance(found, Tag) else None


def _wrap(soup: BeautifulSoup, macro: Tag, element: str, label: str | None) -> Tag:
    """Replace a macro with `element` holding an optional bold label and the macro's rich body."""
    wrapper = soup.new_tag(element)
    if label:
        heading = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = label
        heading.append(strong)
        wrapper.append(heading)
    body = _body(macro, "ac:rich-text-body")
    if body is not None:
        for child in list(body.children):
            wrapper.append(child.extract())
    macro.replace_with(wrapper)
    return wrapper


def _code_block(soup: BeautifulSoup, body: Tag | None, language: str) -> Tag:
    pre = soup.new_tag("pre")
    code = soup.new_tag("code")
    if language:
        code["class"] = [f"language-{language}"]
    code.string = body.get_text() if body is not None else ""
    pre.append(code)
    return pre


def _code_language(element: Tag) -> str:
    code = element.find("code")
    classes = code.get("class", []) if isinstance(code, Tag) else []
    return next((c.removeprefix("language-") for c in classes if c.startswith("language-")), "")


def _link_text(link: Tag) -> str:
    """The text a reader sees, with the linked page's title when the text differs from it."""
    body = link.find(["ac:link-body", "ac:plain-text-link-body"], recursive=False)
    text = " ".join(body.get_text().split()) if body is not None else ""
    target = ""
    if (page := link.find(["ri:page", "ri:blog-post"])) is not None:
        target = str(page.get("ri:content-title", ""))
    elif (attachment := link.find("ri:attachment")) is not None:
        target = str(attachment.get("ri:filename", ""))
    elif (url := link.find("ri:url")) is not None:
        target = str(url.get("ri:value", ""))
    elif (space := link.find("ri:space")) is not None:
        target = str(space.get("ri:space-key", ""))
    elif link.find("ri:user") is not None:
        return text or "@user"  # a mention carries an account id, not a name
    if text and target and text != target:
        return f"{text} ({target})"
    return text or target


def _image_name(image: Tag) -> str:
    attachment, url = image.find("ri:attachment"), image.find("ri:url")
    if isinstance(attachment, Tag) and attachment.get("ri:filename"):
        return str(attachment["ri:filename"])
    if isinstance(url, Tag) and url.get("ri:value"):
        return str(url["ri:value"])
    return str(image.get("ac:alt") or "image")


def _emoji(emoticon: Tag) -> str:
    fallback = str(emoticon.get("ac:emoji-fallback") or "")
    if ESCAPED_UTF16.fullmatch(fallback):
        fallback = json.loads(f'"{fallback}"')
    return fallback or str(emoticon.get("ac:emoji-shortname") or "")


def _tasks(soup: BeautifulSoup, task_list: Tag) -> Tag | None:
    """A task list becomes `[ ]` and `[x]` items. Tasks with no text are left out."""
    items = soup.new_tag("ul")
    for task in task_list.find_all("ac:task", recursive=False):
        body = task.find("ac:task-body", recursive=False)
        if not isinstance(body, Tag) or not _visible_text(body):
            continue
        status = task.find("ac:task-status", recursive=False)
        done = status is not None and status.get_text(strip=True) == "complete"
        item = soup.new_tag("li")
        item.append("[x] " if done else "[ ] ")
        for child in list(body.children):
            item.append(child.extract())
        items.append(item)
    if not items.contents:
        task_list.decompose()
        return None
    task_list.replace_with(items)
    return items


def _adf(soup: BeautifulSoup, extension: Tag) -> Tag | None:
    """Elements of the newer editor. Decision lists are understood; anything else keeps its fallback or text."""
    for attribute in extension.find_all("ac:adf-attribute"):
        attribute.decompose()
    decisions = extension.find("ac:adf-node", attrs={"type": "decision-list"})
    if isinstance(decisions, Tag):
        items = soup.new_tag("ul")
        for decision in decisions.find_all("ac:adf-node", attrs={"type": "decision-item"}):
            text = _visible_text(decision)
            if text:
                item = soup.new_tag("li")
                item.string = f"Decision: {text}"
                items.append(item)
        if items.contents:
            extension.replace_with(items)
            return None
        extension.decompose()
        return None
    fallback = extension.find("ac:adf-fallback")
    keep = fallback if isinstance(fallback, Tag) else extension
    wrapper = soup.new_tag("div")
    for child in list(keep.children):
        wrapper.append(child.extract())
    extension.replace_with(wrapper)
    return wrapper


def _visible_text(element: Tag) -> str:
    """The element's text without edit-only hints, which are removed from it."""
    for hint in element.find_all("ac:placeholder"):
        hint.decompose()
    return " ".join(element.get_text().split())


def _flatten_lists(cell: Tag) -> None:
    """A Markdown table cell is one line, so lists inside a cell become `a; b`."""
    while (found := cell.find(["ul", "ol"])) is not None:
        items = [" ".join(item.get_text().split()) for item in found.find_all("li", recursive=False)]
        found.replace_with(NavigableString("; ".join(item for item in items if item)))


class _Markdown(MarkdownConverter):
    """markdownify with table cells kept on one line and `|` escaped inside them."""

    def convert_td(self, el, text, parent_tags):
        return " " + " ".join(text.split()).replace("|", r"\|") + " |"

    def convert_th(self, el, text, parent_tags):
        return self.convert_td(el, text, parent_tags)


def _tidy(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.replace(chr(0xA0), " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
