---
title: Error codes
parent: Reference
order: 3
---

Error responses look like `{"error": "<code>", "detail": "<text>"}` ([[ADR-003 Error response format]]). Branch on `error`, and show `detail` to people only.

| Code | Status | When | Example `detail` |
|---|---|---|---|
| `invalid_json` | 400 | The body of `POST /items` is not valid JSON | `body is not valid JSON: Expecting value: line 1 column 1 (char 0)` |
| `invalid_item` | 400 | The body is JSON, but not a valid new item | `price must be between 0 and 1000000` |
| `not_found` | 404 | No route for the path, or no item with that id | none |
| `method_not_allowed` | 405 | The path exists, but not with this method, for example `DELETE /items/42` | none |
| `conflict` | 409 | `POST /items` with an id that already exists | `item 42 already exists` |
| `internal_error` | 500 | Anything unexpected. The log has `unhandled error: <ExceptionType>` | none |

## invalid_item details

| Detail | Cause |
|---|---|
| `body must be a JSON object` | The body is a list, a string or a number |
| `unknown field: <names>` | Fields other than `id`, `name` and `price`, for example `stock` |
| `id must be 1-64 letters, digits, '-' or '_'` | Missing or malformed id |
| `name is required` | Missing or blank name |
| `name must be at most 100 characters` | Name too long |
| `price must be a number` | Missing price, or a boolean or text |
| `price must be between 0 and 1000000` | Price below 0 or above 1,000,000 |

::: note
`GET /items/{id}` with an id that does not match the id format returns `404 not_found`, not `400`: the client asked for something that cannot exist.
:::

[[ADR-006 Cursor pagination for the item list]] proposes one more code, `invalid_cursor` (400). It does not exist yet.
