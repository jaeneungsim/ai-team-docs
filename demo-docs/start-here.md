---
title: Start here
parent: Inventory Team
order: 1
---

{toc}

## What we build

Three repos make one system. The item API and the item web pages are a small inventory app. `pr-triage` is a GitHub App on AWS that reviews every PR in the app repos: it checks the ticket and the policy, waits for CI, runs the expected behavior, asks an AI model for a review, and then decides in code. See [[Architecture overview]].

## Access you need

| What | How |
|---|---|
| GitHub | Write access to `jaeneungsim/demo-inventory-api`, `jaeneungsim/demo-inventory-web` and `jaeneungsim/pr-triage` |
| AWS | The SSO profile `jae-dev`: `aws sso login --profile jae-dev`. Region `ap-southeast-2` |
| This space | Confluence space `INV` |

## Set up your machine

::: expand Item API (Python 3.13, uv, Docker)
```bash
git clone https://github.com/jaeneungsim/demo-inventory-api.git && cd demo-inventory-api
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
scripts/setup-hooks.sh
.venv/bin/ruff check . && .venv/bin/pytest
```

To run the API on your machine with DynamoDB Local:

```bash
docker run --rm -p 8000:8000 amazon/dynamodb-local:3.3.1
.venv/bin/python scripts/seed.py
.venv/bin/python scripts/local_server.py --port 8080 > server.log &
curl http://127.0.0.1:8080/items/42
```
:::

::: expand Item web pages (Node 22)
```bash
git clone https://github.com/jaeneungsim/demo-inventory-web.git && cd demo-inventory-web
scripts/setup-hooks.sh
npm test
python3 -m http.server 5173 --directory src
```

Open `http://localhost:5173/index.html`. `src/config.js` already points at the local API on port 8080.
:::

::: expand pr-triage (Python 3.13, Node 22 for CDK)
```bash
git clone https://github.com/jaeneungsim/pr-triage.git && cd pr-triage
uv venv --python 3.13 .venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest && .venv/bin/ruff check .
cd infra && npm ci && npm test && npx cdk synth
```
:::

## Your first week

1. Read [[Branches, commits and PR titles]] and [[Writing the expected behavior block]].
2. Pick a small ticket with status `todo` from `demo-inventory-api/tickets/`.
3. Open a PR and read what pr-triage says about it before you ask a person.
4. Read the [[Runbooks]] once, so you know they exist before you need them.

::: tip
The seed data is the same in every environment: items 41, 42 and 43. Item 43 has no stock, so it is the quickest way to see the sold-out case.
:::
