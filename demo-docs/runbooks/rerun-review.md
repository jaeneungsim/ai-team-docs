---
title: Review a PR again or change the review level
parent: Runbooks
order: 5
---

## Review the current commit again

Use this after a model outage, or after reviews were switched off and on again. From the `pr-triage` repo:

```bash
.venv/bin/python scripts/rerun_review.py --repo demo-inventory-api --pr 1 --profile jae-dev
```

The script starts a new review run with the input of the PR's latest run, so the result belongs to the PR's current commit. Redelivering the webhook from GitHub does not work, because pr-triage ignores delivery ids it has already handled.

A new commit on the PR starts a new review by itself; you do not need the script then.

## Change the level

| Level | Adds | Where PR code runs |
|---|---|---|
| v1 | policy, CI result, AI review of the code against the ticket | nowhere |
| v2 | test relevance, expected behavior run in CI, read-only check on dev after the merge | GitHub Actions |
| v3 | the ticket's PRs deployed together to an AWS preview, expected behavior run there | a preview per ticket |

```bash
scripts/set_level.sh v2 --profile jae-dev
```

The script sets `/pr-triage/config/level` and the repo variable `TRIAGE_LEVEL` in both app repos. Reviews that already started keep the level they started with.

## Change the mode

```bash
aws ssm put-parameter --name /pr-triage/config/mode --value advisory --type String --overwrite \
  --profile jae-dev --region ap-southeast-2
```

The values are `advisory` and `auto-approve`. See [[ADR-007 Advisory mode by default, auto-approve only when code can vouch]].
