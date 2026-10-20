---
title: Find the logs for a request
parent: Runbooks
order: 3
---

Every API response has an `x-request-id` header. The same id is in every log line for that request.

## Where the logs are

| Environment | Log group | Kept for |
|---|---|---|
| dev | `/aws/lambda/inv-api-dev-handler` | 14 days |
| Ticket preview | `/aws/lambda/inv-api-preview-<stage>-handler`, for example `/aws/lambda/inv-api-preview-inv-123-handler` | 3 days, and removed with the preview |

## Get the request id

```bash
curl -si "${API_URL%/}/items/42" | grep -i x-request-id
```

## Search with the CLI

```bash
aws logs filter-log-events --profile jae-dev --region ap-southeast-2 \
  --log-group-name /aws/lambda/inv-api-dev-handler \
  --filter-pattern '{ $.request_id = "<request-id>" }'
```

## Search with Logs Insights

```sql
fields @timestamp, level, message, route, status
| filter request_id = "<request-id>"
| sort @timestamp asc
```

## Reading the lines

Each line is JSON with the fields `level`, `request_id`, `message`, `route` and `status`.

| Response status | Log level |
|---|---|
| 500 and above | `ERROR` |
| 400 to 499 | `WARNING` |
| below 400 | `INFO` |

A 500 also writes the line `unhandled error: <ExceptionType>` before the `request handled` line. The client only sees `{"error": "internal_error"}`.

The `log` items in an expected behavior block (`no_level: ERROR`) look at the same request id. Lambda's own `START`, `END` and `REPORT` lines are not JSON and carry the id as plain text.
