---
title: Clean up a stuck preview
parent: Runbooks
order: 6
---

Previews normally clean up after themselves. `preview-destroy` and `web-preview-destroy` run when a PR closes, and the hourly `PreviewCleanup` job removes previews that are older than 24 hours or have no open PR. Use this page when a preview is still there after a day.

## Find leftover previews

```bash
aws cloudformation list-stacks --profile jae-dev --region ap-southeast-2 \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED \
  --query "StackSummaries[?starts_with(StackName, 'inv-api-preview-')].[StackName,StackStatus]" \
  --output table
```

## Remove an API preview

```bash
aws cloudformation delete-stack --stack-name inv-api-preview-inv-123 \
  --role-arn arn:aws:iam::<account-id>:role/inv-preview-cfn-exec \
  --profile jae-dev --region ap-southeast-2
```

Pass the role: the stack was created through it, and it holds the permissions to delete the app's resources.

## Remove a web preview

```bash
aws s3 rm "s3://inv-web-preview-<account-id>-ap-southeast-2/inv-123/" --recursive \
  --profile jae-dev --region ap-southeast-2
```

::: warning
Check the stage name twice. `inv-api-dev` and the `dev/` prefix are the dev environment, not previews. Deleting them takes dev down until the next `deploy-dev` run.
:::

## If the delete fails

A stack in `DELETE_FAILED` usually means the CloudFormation role cannot delete one resource. Read the events with `aws cloudformation describe-stack-events --stack-name <name>`, fix the role in pr-triage if needed, and delete again.
