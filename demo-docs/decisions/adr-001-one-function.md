---
title: ADR-001 One Lambda function behind the HTTP API
parent: Decisions
order: 1
---

{status:Accepted|Green} · Decided 2026-10-11 · Ticket INV-100

## Context

The item API has four routes: `GET /health`, `GET /items`, `POST /items` and `GET /items/{id}`. Every route reads or writes the same DynamoDB table, and traffic is low.

## Decision

One Lambda function, `<stack>-handler`, serves every route through the HTTP API `$default` route. The function routes requests itself, with the `PATHS` and `ROUTES` tables in `src/inventory/handler.py`.

- An unknown path returns `404 {"error": "not_found"}`.
- A known path with a method it does not support returns `405 {"error": "method_not_allowed"}`.

## Consequences

- One log group and one IAM role per environment, which keeps previews cheap and their logs easy to read.
- All routes share one memory size and one timeout.
- Revisit this when routes need different permissions, or when one route needs much more memory than the others.
