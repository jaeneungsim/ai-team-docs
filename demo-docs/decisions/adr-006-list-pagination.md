---
title: ADR-006 Cursor pagination for the item list
parent: Decisions
order: 6
---

{status:Proposed|Blue} · Proposed 2026-10-12 · Ticket INV-125

::: info Not decided yet
Do not build on this until the status is Accepted. Comment on this page with objections.
:::

## Context

INV-125 asks for at most 20 items per response from `GET /items`, with a `next` cursor that returns the following page. Today the handler scans the whole table, sorts the items (numeric ids first in number order, then the other ids) and returns all of them.

## Options

| Option | Order across pages | Cost per request | Notes |
|---|---|---|---|
| A. DynamoDB scan pages, cursor is `LastEvaluatedKey` | Not stable | One page of reads | The current sort order is lost |
| B. Read all, sort, return 20, cursor is the last id returned | Stable | Grows with the table | Same order as today |
| C. Add an index with a sort key | Stable | One page of reads | Needs a table change and a backfill |

## Proposal

Option B while the table has fewer than 1,000 items, then revisit with option C.

- The cursor is opaque to clients: base64 of the last id returned. Clients send it back as `?cursor=<value>`.
- The response keeps the `items` array and adds `next` only when more items exist.
- An invalid cursor returns `400 {"error": "invalid_cursor"}`.

## Open questions

- Should clients be able to ask for fewer than 20 items?
- Does the web list page need a "load more" button in the same ticket?
