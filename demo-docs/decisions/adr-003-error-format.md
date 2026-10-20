---
title: ADR-003 Error response format
parent: Decisions
order: 3
---

{status:Accepted|Green} · Decided 2026-10-11 · Ticket INV-100

## Decision

Every error response is JSON with a stable code and an optional detail for people:

```json
{"error": "invalid_item", "detail": "price must be between 0 and 1000000"}
```

- `error` is a snake_case code. Clients may branch on it, so a code never changes its meaning.
- `detail` is for people. Clients must not parse it, and its wording may change at any time.
- Every response, error or not, carries the `x-request-id` header. Quote it when you report a problem.
- A 500 response is always `{"error": "internal_error"}`. The exception type goes to the log, never to the client.

The codes and their status codes are listed in [[Error codes]].

## Consequences

- Adding a code is fine. Renaming or reusing one needs a new decision record.
- `openapi.yaml` describes the shape once, as the `Error` schema.
