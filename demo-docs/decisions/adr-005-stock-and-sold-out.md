---
title: ADR-005 Return stock and derive sold_out
parent: Decisions
order: 5
---

{status:Accepted|Green} · Decided 2026-10-12 · Tickets INV-123, INV-124 · Supersedes [[ADR-002 Keep stock out of item responses]]

## Context

- INV-123: show the stock quantity on the item detail page.
- INV-124: mark items with zero stock as sold out.

## Decision

Item responses include two fields:

| Field | Type | Meaning |
|---|---|---|
| `stock` | integer, 0 or more | Units in stock |
| `sold_out` | boolean | `true` when `stock` is 0 or less |

The API derives `sold_out` in one place, `public_item()` in `src/inventory/handler.py`. It is never stored, so it cannot disagree with `stock`.

## Consequences

- `POST /items` creates items with `stock` 0, because restocking is a separate flow. A new item is therefore sold out until it is restocked.
- The web detail page still decides from `stock`: it shows "Out of stock" at 0 and, for example, "5 in stock" otherwise. Switching it to `sold_out` is a follow-up that needs its own ticket.
- Seed item 43 (Dot grid notebook) has stock 0 and is the reference case for tests and previews.
