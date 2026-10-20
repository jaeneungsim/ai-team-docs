# Storage format fixtures

Page bodies in Confluence storage format, the way the sync reads them from
`GET /wiki/api/v2/spaces/{id}/pages?status=current&body-format=storage`. The converter tests use them.

| File | Covers |
|---|---|
| `start-here.html` | toc, expand, code, tip, table |
| `adr-002-no-stock-in-responses.html` | status, warning, page links, `&middot;` |
| `adr-006-list-pagination.html` | status, info, table |
| `decisions-index.html` | children, status |
| `deploy-to-dev.html` | code, note, table, `&rarr;` |
| `error-codes.html` | note, table, page links with `ri:version-at-save` |
| `editor-elements.html` | elements that only the Confluence editor writes (see below) |
| `editor-page.html` | a page made in the editor: filled tasks, a decision, an @mention, an info panel |

## Pages from the demo site

The first six files are demo pages exactly as Confluence stored them on 2026-10-19, after
`scripts/upload_demo_docs.py` uploaded them from `demo-docs/`. Confluence made three changes to
every uploaded page, and nothing else:

- Macros get `ac:schema-version` and `ac:macro-id`.
- A link to a page that already existed gets `ri:version-at-save`.
- Characters such as `·` and `→` become `&middot;` and `&rarr;`.

Named entities like these are not valid XML, so read storage format with an HTML parser.

## editor-elements.html

Written by hand. It copies the structure of the pages that Confluence's built-in templates create,
with new text, because the template text belongs to Atlassian:

- `ac:placeholder`: hint text that only shows while editing
- `ac:emoticon`: `ac:emoji-fallback` is sometimes the emoji itself and sometimes an escaped
  UTF-16 pair such as `\uD83D\uDCD8`; Atlassian's own emoji fall back to a short name like `:plus:`
- `ac:macro ac:name="details"`: the page properties macro in its older form
- tables with `colgroup`, `data-highlight-colour`, a header column instead of a header row, lists
  inside cells, and empty cells (`<p />`, `<p><br /></p>`)
- `ac:task-list` and `ac:adf-extension` (a decision list), both empty as in the templates

## editor-page.html

A page made in the Confluence editor on 2026-10-19, as Confluence stored it, except that the
mention's account id is replaced with `000000:00000000-0000-0000-0000-000000000000`. It fills in
what the templates left empty:

- A filled task keeps its text in `<span class="placeholder-inline-tasks">` inside `ac:task-body`.
  Despite the class name, that is the task's text, not a hint.
- A decision keeps its text in `ac:adf-content` and repeats it in `ac:adf-fallback`.
- A mention stores only the account id (`ri:user`), so the converter writes `@user`.
- The info panel has a `containerLevel` parameter instead of a title, and paragraphs carry
  `local-id` attributes.
