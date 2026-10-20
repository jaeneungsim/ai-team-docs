---
title: Inventory Team
home: true
---

The Inventory Team builds and runs a small inventory app and the service that reviews its pull requests.

## What we own

| Part | Repo | What it does |
|---|---|---|
| Item API | `demo-inventory-api` | HTTP API, one Lambda function and a DynamoDB table. Holds the tickets in `tickets/` |
| Item web pages | `demo-inventory-web` | Static item list and item detail pages |
| PR review service | `pr-triage` | Reviews every PR in the two app repos before a person does |

Everything runs in one AWS account in `ap-southeast-2` (Sydney). There is a `dev` environment and one preview per ticket. Production is out of scope for this team.

## Where to look

- New here? Read [[Start here]].
- Why something is the way it is: [[Decisions]]
- How to do an operational task: [[Runbooks]]
- How we name, write and review changes: [[Team conventions]]
- Names, routes, error codes and terms: [[Reference]]

## Current focus

- INV-125: page the item list, 20 items per page. The design is still a proposal: [[ADR-006 Cursor pagination for the item list]].
- Keep auto-approve on for `dev` and read the morning digest for surprises.

::: note How these pages are kept
If a page and the code disagree, the code wins. Fix the page in the same week, and say in the page what changed.
:::
