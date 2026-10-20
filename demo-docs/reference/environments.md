---
title: Environments and resource names
parent: Reference
order: 4
---

## Environments

| Environment | Stage | When it exists |
|---|---|---|
| dev | `dev` | Always. Deployed on every merge into `dev` |
| Ticket preview | the ticket key in lower case, for example `inv-123` | While the ticket has an open PR, and at most about a day |

There is no production environment.

## API resources

| Resource | dev | Preview for INV-123 |
|---|---|---|
| Stack | `inv-api-dev` | `inv-api-preview-inv-123` |
| Function | `inv-api-dev-handler` | `inv-api-preview-inv-123-handler` |
| Log group | `/aws/lambda/inv-api-dev-handler`, kept 14 days | `/aws/lambda/inv-api-preview-inv-123-handler`, kept 3 days |
| Table | `inv-api-dev-items` | `inv-api-preview-inv-123-items` |
| HTTP API | `inv-api-dev` | `inv-api-preview-inv-123` |

Each stack has the outputs `ApiUrl`, `FunctionName`, `LogGroupName` and `TableName`.

## Web

| What | Value |
|---|---|
| Bucket | `inv-web-preview-<account-id>-ap-southeast-2`, one bucket for dev and the previews |
| dev pages | the prefix `dev/` |
| Preview pages | the prefix `inv-123/`, for example `https://<domain>/inv-123/item.html?id=42` |

## pr-triage settings (SSM)

| Parameter | Values |
|---|---|
| `/pr-triage/config/enabled` | `on` or `off`. The budget stop sets `off`; a person sets it back |
| `/pr-triage/config/level` | `v1`, `v2` or `v3` |
| `/pr-triage/config/mode` | `advisory` or `auto-approve` |
| `/pr-triage/config/limits` | JSON: `daily_reviews` 10, `monthly_usd` 5, `max_input_tokens` 30000, `max_output_tokens` 3000 |
| `/pr-triage/config/model` | JSON: the model or inference profile id, and its price per million tokens |
| `/pr-triage/config/allowed-authors` | JSON list of the GitHub logins whose PRs may use the AI review |

## Repo variables

Both app repos have `AWS_REGION`, `PREVIEW_ROLE_ARN`, `DEV_ROLE_ARN` and `TRIAGE_LEVEL`. The API repo also has `CFN_EXEC_ROLE_ARN`, and the web repo has `WEB_PREVIEW_BUCKET` and `WEB_PREVIEW_DOMAIN`. pr-triage's `scripts/configure_demo_repos.sh` sets them all.
