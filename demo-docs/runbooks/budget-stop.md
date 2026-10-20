---
title: Turn AI reviews back on after a budget stop
parent: Runbooks
order: 4
---

## What stops AI reviews

| Limit | Where it is set | What happens |
|---|---|---|
| 10 reviews a day | `/pr-triage/config/limits`, `daily_reviews` | Later PRs that day skip the AI review |
| $5 of AI cost a month, counted by the app | `/pr-triage/config/limits`, `monthly_usd` | Later PRs that month skip the AI review |
| AWS budget `pr-triage-account-monthly`: email at $5, stop at $8 | AWS Budgets | The kill switch sets `/pr-triage/config/enabled` to `off` |

When the AI review is skipped, policy checks and CI still run, and the PR gets "needs human review". A limit never turns into an approval.

The app's own count reacts first. AWS Budgets updates only a few times a day, so it can react hours late; it is the backstop for when the app's count is wrong.

## Turn reviews back on after the $8 stop

1. Find out what spent the money: open Billing → Bills and look at the Amazon Bedrock line.
2. Fix the cause first, for example an evaluation script that ran in a loop.
3. Switch reviews back on:

```bash
aws ssm put-parameter --name /pr-triage/config/enabled --value on --type String --overwrite \
  --profile jae-dev --region ap-southeast-2
```

4. PRs reviewed while the switch was off keep "needs human review". Review them again with [[Review a PR again or change the review level]].

::: warning
The switch stays `off` until a person sets it back. Do not raise `monthly_usd` to get past a stop when you do not know why it fired.
:::

## When the daily or monthly count is the limit

Nothing needs to be switched on. The daily count starts again the next day, and the monthly cost the next month. Review urgent PRs by hand in the meantime.
