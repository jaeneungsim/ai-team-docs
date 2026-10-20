---
title: Writing the expected behavior block
parent: Team conventions
order: 2
---

Every PR description has a section `## Expected behavior` with a fenced block whose info string is exactly `yaml expected-behavior`. The block is part of the PR description, not a file in the repo.

## Example

```yaml
- id: B1
  covers: [R1]
  type: api
  request: GET /items/42
  expect:
    status: 200
    body_has: [stock]
- id: B2
  covers: [R1]
  type: log
  after: B1
  expect:
    no_level: ERROR
- id: B3
  covers: [R2]
  type: ui
  page: /item.html?id=42
  step: The detail page for item 42 shows the stock quantity.
```

## Rules

- Derive the items from the ticket requirements (`R1`, `R2`, ...), not from the code you wrote. Every item lists the requirements it covers in `covers`.
- `api` items describe a response, `log` items say "no errors for this request", and `ui` items are what a person has to look at.
- Only describe routes that exist in `openapi.yaml` after your change.
- Update the block whenever you push more commits.

## Fields

| Field | Applies to | Meaning |
|---|---|---|
| `id` | all | `B<n>`, unique in the block |
| `covers` | all | requirement ids from the ticket |
| `type` | all | `api`, `log` or `ui` |
| `request` | api | `"<METHOD> <path>"`; the path starts with `/` and has no host |
| `expect.status` | api | the HTTP status |
| `expect.body_has` | api | keys that must exist; dotted paths such as `item.stock` are allowed |
| `expect.body_not_has` | api | keys that must not exist |
| `expect.body_includes` | api | an object that must appear in the body (deep subset match) |
| `after` | log | the `api` item whose request the log check looks at |
| `expect.no_level` | log | `ERROR`: no line at ERROR or above for that request |
| `expect.has_message` | log | text that must appear in a log line for that request |
| `step` | ui | what a person should check |
| `page` | ui | the page path on the web preview |

## Where it runs

| Level | Where the `api` and `log` items run |
|---|---|
| v1 | nowhere; the AI review reads them against the code |
| v2 | in CI, against the PR's API with DynamoDB Local |
| v3 | in CI, and on the ticket's AWS preview |

After the merge, only the `GET` items run again, read-only, against dev. `ui` items always stay with a person, and a PR with `ui` items is never auto-approved.
