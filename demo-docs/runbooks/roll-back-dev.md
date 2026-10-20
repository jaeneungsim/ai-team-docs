---
title: Roll back a bad deploy on dev
parent: Runbooks
order: 2
---

Use this when `dev` is broken after a merge: the post-merge check failed, or a route answers differently from its ticket.

## 1. Find the bad commit

Every merge into `dev` is one squash commit whose message starts with the ticket key.

```bash
git switch dev && git pull --ff-only
git log --oneline -5
```

## 2. Fast path: redeploy the last good commit

Re-running an old `deploy-dev` run deploys that run's commit again. Find the run of the last good commit and re-run it:

```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

::: warning
This only changes what is deployed. The `dev` branch still has the bad commit, and the next merge deploys it again. Always do step 3 straight after.
:::

## 3. Revert the commit in a PR

```bash
git switch -c INV-124-revert-sold-out
git revert --no-edit <bad-commit-sha>
git commit --amend -m "INV-124: revert treat zero stock as sold out"
git push -u origin INV-124-revert-sold-out
```

Open the PR with the title `INV-124 Revert treat zero stock as sold out`, the type `bugfix`, and an expected behavior block that describes the behavior you are restoring. pr-triage reviews it like any other PR. When it is merged, `deploy-dev` deploys the reverted code.

Replace `INV-124` and the names with your own ticket. The commit-msg hook rejects a message without the ticket key.

## 4. After the rollback

- Check that the post-merge comment on the revert PR is green.
- Data is not rolled back. If the bad code wrote bad items, fix them separately. The seed items 41, 42 and 43 are in `seed/items.json`.
- Add a note to the ticket and bring it to the next team check-in.
