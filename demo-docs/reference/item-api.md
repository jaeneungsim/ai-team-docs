---
title: Item API
parent: Reference
order: 2
---

The contract is `openapi.yaml` in `demo-inventory-api`. This page is a summary.

## Routes

| Route | Success | Errors |
|---|---|---|
| `GET /health` | `200 {"ok": true}` | |
| `GET /items` | `200 {"items": [...]}` | |
| `GET /items/{id}` | `200` with the item | `404 not_found` |
| `POST /items` | `201` with the created item | `400 invalid_json`, `400 invalid_item`, `409 conflict` |

Any other method on these paths returns `405 method_not_allowed`.

## Item fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | 1 to 64 letters, digits, `-` or `_` |
| `name` | string | 1 to 100 characters, trimmed |
| `price` | number | 0 to 1,000,000 |
| `stock` | integer | 0 or more. Not accepted by `POST /items`; new items start at 0 |
| `sold_out` | boolean | `true` when `stock` is 0 or less |

`POST /items` accepts only `id`, `name` and `price`. Any other field is rejected with `400 invalid_item`. Why `sold_out` exists: [[ADR-005 Return stock and derive sold_out]].

## Order of the list

`GET /items` returns every item: numeric ids first in number order (`41`, `42`, `43`, ..., `100`), then the other ids in text order. Paging is proposed in [[ADR-006 Cursor pagination for the item list]].

## Examples

```bash
curl -s "${API_URL%/}/items/43"
# {"id": "43", "name": "Dot grid notebook", "price": 8.0, "stock": 0, "sold_out": true}

curl -s -X POST "${API_URL%/}/items" -H 'content-type: application/json' \
  -d '{"id": "44", "name": "Desk lamp", "price": 39.5}'
# {"id": "44", "name": "Desk lamp", "price": 39.5, "stock": 0, "sold_out": true}
```

Every response has the `x-request-id` header. See [[Find the logs for a request]].
