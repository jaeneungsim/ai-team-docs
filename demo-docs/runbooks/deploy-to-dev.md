---
title: Deploy to dev
parent: Runbooks
order: 1
---

## How dev gets deployed

Nobody deploys `dev` by hand. Merging a PR into the `dev` branch starts the `deploy-dev` workflow:

| Repo | What `deploy-dev` does |
|---|---|
| `demo-inventory-api` | `cdk deploy` of the stack `inv-api-dev` |
| `demo-inventory-web` | publishes `src/` to the `dev/` prefix of the web bucket |

After the API deploy, pr-triage runs a read-only check on dev: it calls the `GET` items from the merged PR's expected behavior and comments on the PR. If the check fails, the PR gets the label `triage: post-merge failed`.

## Check a deploy

1. In GitHub, open Actions → `deploy-dev` and confirm that the run for your merge commit is green.
2. Call the health route:

```bash
API_URL=$(aws cloudformation describe-stacks --stack-name inv-api-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text \
  --profile jae-dev --region ap-southeast-2)
curl -s "${API_URL%/}/health"
```

The answer is `{"ok": true}`. The `ApiUrl` output ends with a slash; `${API_URL%/}` removes it so that the path does not start with a double slash.

## When the deploy fails

1. Read the stack events:

```bash
aws cloudformation describe-stack-events --stack-name inv-api-dev --max-items 20 \
  --profile jae-dev --region ap-southeast-2
```

2. The usual cause is that the CloudFormation role `inv-preview-cfn-exec` lacks a permission for a new resource type. On 2026-10-11 it lacked `apigateway:TagResource`. That role is defined in pr-triage (`infra/lib/preview-platform-stack.ts`), so the fix is a pr-triage PR, not an app PR.
3. After the fix, re-run the failed `deploy-dev` run: Actions → the run → Re-run all jobs.

::: note Deploying from a laptop
This is a last resort for when the workflow itself is broken. From `infra/` in the API repo, with a session that may pass the CloudFormation role:

```bash
npx cdk deploy --require-approval never --role-arn "$CFN_EXEC_ROLE_ARN" -c stage=dev
```
:::

Production is out of scope for this team. Promotion beyond `dev` is always done by a person.
