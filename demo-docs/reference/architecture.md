---
title: Architecture overview
parent: Reference
order: 1
---

Everything runs in one AWS account in `ap-southeast-2`. All infrastructure is CDK in TypeScript, and the Lambda code is Python 3.13.

## The app

```text
browser ── CloudFront ── S3 (web pages)
   │
   └── API Gateway HTTP API ($default route) ── Lambda <stack>-handler ── DynamoDB <stack>-items
```

- **API:** one HTTP API per environment, CORS `*`, throttled at 10 requests a second with bursts of 20. One Lambda function serves every route ([[ADR-001 One Lambda function behind the HTTP API]]).
- **Table:** partition key `id` (string), on-demand capacity. Every new stack is seeded with items 41, 42 and 43.
- **Web:** two static pages, `index.html` (item list) and `item.html?id=42` (item detail), in one bucket behind one CloudFront distribution with caching disabled. `config.js` is written at deploy time with the API URL.

## The review service (pr-triage)

```text
GitHub ── webhook ──▶ API Gateway ──▶ ingest Lambda ──▶ SQS ──▶ dispatcher ──▶ Step Functions (one run per commit)
```

A run has eight steps: collect context, check policy, wait for CI, check results, AI review, validate the answer, decide, publish. The AI suggests; code decides. Run records and costs are in DynamoDB, the collected context in S3, and the settings in SSM under `/pr-triage/config/`.

Two scheduled jobs:

- `MorningDigest`: 08:00 Monday to Friday, Sydney time. Posts a summary of the PRs reviewed overnight as a comment on an issue in `demo-inventory-api`.
- `PreviewCleanup`: every hour. Removes previews older than 24 hours or without an open PR.

## Deploys

GitHub Actions gets AWS credentials through OIDC. Each role trusts one repo and one event:

| Role | Used by |
|---|---|
| `inv-gha-preview-api` | API previews for PRs |
| `inv-gha-dev-api` | API deploys to dev |
| `inv-gha-preview-web` | web previews for PRs |
| `inv-gha-dev-web` | web deploys to dev |

The API roles deploy through one CloudFormation role, `inv-preview-cfn-exec`, and every role the app creates carries the permissions boundary `inv-preview-boundary`.
