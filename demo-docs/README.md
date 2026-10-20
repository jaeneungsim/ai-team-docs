# Demo docs

The Confluence pages of a fictional team that runs the demo app from
[pr-triage](https://github.com/jaeneungsim/pr-triage): the item API, the item web pages and the
review service. The facts match those three repos as of October 2026. There is no real team; the
attendees in meeting notes are roles.

`scripts/upload_demo_docs.py` uploads these files to the demo Confluence space. They are also
the corpus that the sync, the search and the evaluation use.

## Format

Each file starts with front matter:

```markdown
---
title: Roll back a bad deploy on dev
parent: Runbooks
order: 2
---
```

- `title` must be unique; links use it.
- `parent` is the title of the parent page. The space homepage has `home: true` instead.
- `order` sorts siblings. `stage: v2` holds a page back until that level (safety test pages).

The body is Markdown with tables, plus a few Confluence macros (see `scripts/md_to_storage.py`):

| Write | Becomes |
|---|---|
| `::: info Title` … `:::` | info panel (also `note`, `warning`, `tip`) |
| `::: expand Title` … `:::` | expand macro |
| `{toc}`, `{children}` alone in a paragraph | table of contents, child pages |
| `{status:Accepted\|Green}` | status lozenge |
| `[[Page title]]`, `[[Page title\|text]]` | link to another page |
| a fenced code block | code macro with the fence language |
