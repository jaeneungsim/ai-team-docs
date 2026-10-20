"""Turn the demo docs (Markdown plus a few Confluence extensions) into Confluence storage format.

On top of CommonMark and tables:

    ::: info Title             info, note, warning or tip panel (the title is optional), closed by :::
    ::: expand Title           expand macro
    {toc}  {children}          table of contents or child pages macro, alone in a paragraph
    {status:Accepted|Green}    status lozenge (inline)
    [[Page title]]             link to a page in the same space; [[Page title|link text]] too

Fenced code blocks become code macros that keep the fence language.
"""

from __future__ import annotations

import re
from html import escape

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from mdit_py_plugins.container import container_plugin

PANELS = ("info", "note", "warning", "tip")
LANGUAGES = {"sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash", "py": "python", "yml": "yaml"}
STATUS = re.compile(r"\{status:([^|{}\n]+)\|(Grey|Red|Yellow|Green|Blue|Purple)\}")
PAGE_LINK = re.compile(r"\[\[([^\[\]|\n]+)(?:\|([^\[\]\n]+))?\]\]")
BLOCK_MACROS = {
    "<p>{toc}</p>": '<ac:structured-macro ac:name="toc" />',
    "<p>{children}</p>": '<ac:structured-macro ac:name="children" />',
}


def convert(markdown: str) -> str:
    html = _parser().render(markdown)
    for placeholder, macro in BLOCK_MACROS.items():
        html = html.replace(placeholder, macro)
    return html


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "xhtmlOut": True}).enable("table")
    for name in (*PANELS, "expand"):
        container_plugin(md, name, render=_container(name))
    md.inline.ruler.before("link", "page_link", _page_link)
    md.inline.ruler.before("link", "status", _status)
    md.add_render_rule("page_link", _render_page_link)
    md.add_render_rule("status", _render_status)
    md.add_render_rule("fence", _render_fence)
    md.add_render_rule("code_block", _render_fence)
    # Storage format keeps every table row in one tbody.
    md.add_render_rule("table_open", lambda *_: "<table><tbody>\n")
    md.add_render_rule("table_close", lambda *_: "</tbody></table>\n")
    for rule in ("thead_open", "thead_close", "tbody_open", "tbody_close"):
        md.add_render_rule(rule, lambda *_: "")
    return md


def _container(name: str):
    def render(self, tokens, idx, options, env) -> str:
        token = tokens[idx]
        if token.nesting == -1:
            return "</ac:rich-text-body></ac:structured-macro>\n"
        title = token.info.strip()[len(name) :].strip()
        param = f'<ac:parameter ac:name="title">{escape(title, quote=False)}</ac:parameter>' if title else ""
        return f'<ac:structured-macro ac:name="{name}">{param}<ac:rich-text-body>\n'

    return render


def _render_fence(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    language = token.info.strip().split(" ", 1)[0].lower() if token.info else ""
    language = LANGUAGES.get(language, language)
    param = f'<ac:parameter ac:name="language">{escape(language)}</ac:parameter>' if language else ""
    body = _cdata(token.content.rstrip("\n"))
    return (
        f'<ac:structured-macro ac:name="code">{param}'
        f"<ac:plain-text-body>{body}</ac:plain-text-body></ac:structured-macro>\n"
    )


def _page_link(state: StateInline, silent: bool) -> bool:
    match = PAGE_LINK.match(state.src, state.pos, state.posMax)
    if not match:
        return False
    if not silent:
        token = state.push("page_link", "", 0)
        token.meta = {"title": match[1].strip(), "text": (match[2] or match[1]).strip()}
    state.pos = match.end()
    return True


def _render_page_link(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    return (
        f'<ac:link><ri:page ri:content-title="{escape(meta["title"])}" />'
        f"<ac:plain-text-link-body>{_cdata(meta['text'])}</ac:plain-text-link-body></ac:link>"
    )


def _status(state: StateInline, silent: bool) -> bool:
    match = STATUS.match(state.src, state.pos, state.posMax)
    if not match:
        return False
    if not silent:
        token = state.push("status", "", 0)
        token.meta = {"title": match[1].strip(), "colour": match[2]}
    state.pos = match.end()
    return True


def _render_status(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    return (
        '<ac:structured-macro ac:name="status">'
        f'<ac:parameter ac:name="colour">{meta["colour"]}</ac:parameter>'
        f'<ac:parameter ac:name="title">{escape(meta["title"], quote=False)}</ac:parameter>'
        "</ac:structured-macro>"
    )
