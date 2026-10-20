---
title: ADR-002 Keep stock out of item responses
parent: Decisions
order: 2
---

{status:Superseded|Grey} · Decided 2026-10-11 · Ticket INV-100 · Superseded on 2026-10-12 by [[ADR-005 Return stock and derive sold_out]]

::: warning
This decision is no longer in force. Item responses now include `stock` and `sold_out`.
:::

## Context

The table needed a `stock` attribute from the start, because restocking is planned as a separate flow. Nothing on the web pages showed stock yet.

## Decision

Store `stock` in the table, but return only `id`, `name` and `price` from `GET /items` and `GET /items/{id}`.

## Why it was replaced

INV-123 asked for the stock quantity on the item detail page, so the API had to return it.
