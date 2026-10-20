# Comparison scene

Question: dev broke right after something got merged. What is the quickest way to get the previous working version running again?

## before the edit (runbook version 1) (2026-10-20T09:24:38+00:00)

| Agent | Suggests `gh run rerun` | Says not to re-run | Mentions revert |
|---|---|---|---|
| copy | yes | no | yes |
| managed KB | yes | no | yes |
| team-docs | yes | no | no |

**copy**

According to the Roll back a bad deploy on dev runbook, the quickest way is the **fast path: redeploy the last good commit**.

Use these commands:

```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

Find the run of the last good commit and re-run it. This deploys that run's commit again without needing to make code changes.

**Important:** This only changes what is deployed—the `dev` branch still has the bad commit. You must follow step 3 immediately after to revert the commit in a PR, otherwise the next merge will deploy the bad code again.

**managed KB**

According to the "Roll back a bad deploy on dev" docs (page [1]), the quickest way is the **fast path**:

1. Find the last good commit's deploy run using:
   ```bash
   gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
   ```

2. Re-run that old deploy:
   ```bash
   gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
   ```

This redeploys the last good commit immediately without changing the branch.

**Important:** This only fixes what's deployed. The bad commit stays in the dev branch, so the next merge will deploy it again. You must immediately do step 3: create a revert PR to remove the bad commit from the branch itself.

**team-docs**

Based on the docs, the quickest way is the **fast path** from page [1]:

1. Find the last good commit's deploy run:
```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
```

2. Re-run that deployment:
```bash
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

This redeploys the last good commit to dev immediately.

**Important:** The docs warn that this only fixes what's deployed—the `dev` branch still has the bad commit. You must do step 3 (from page [5]) right after to fix the branch itself, or the next merge will deploy the bad commit again.

## after the edit: our search synced, the knowledge base not yet (2026-10-20T09:32:17+00:00)

| Agent | Suggests `gh run rerun` | Says not to re-run | Mentions revert |
|---|---|---|---|
| copy | yes | no | yes |
| managed KB | yes | no | yes |
| team-docs | no | yes | yes |

**copy**

According to the Roll back a bad deploy on dev runbook, the quickest way is the **fast path: redeploy the last good commit**.

Use these commands:

```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

Find the run of the last good commit and re-run it. This deploys that run's commit again without needing to make code changes.

**Important:** This only changes what is deployed—the `dev` branch still has the bad commit. You must follow step 3 immediately after to revert the commit in a PR, otherwise the next merge will deploy the bad code again.

**managed KB**

According to the "Roll back a bad deploy on dev" docs (page [1]), the quickest way is the **fast path**:

1. Find the last good commit's deploy run using:
   ```bash
   gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
   ```

2. Re-run that old deploy:
   ```bash
   gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
   ```

This redeploys the last good commit immediately without changing the branch.

**Important:** This only fixes what's deployed. The bad commit stays in the dev branch, so the next merge will deploy it again. You must immediately do step 3: create a revert PR to remove the bad commit from the branch itself.

**team-docs**

According to the docs on rolling back a bad deploy on dev, the quickest way is to use the revert PR. 

From page [1] "Roll back a bad deploy on dev > 2. Do not re-run old deploys" (version 2, edited 2026-10-20 09:24 UTC):

> Re-running an old `deploy-dev` run used to be the fast path. The team stopped on 2026-10-20: the redeployed commit only lasts until the next merge, which deploys the bad commit again. Go straight to step 3. The revert PR is the only way back.

So you should skip re-running old deploys and go straight to creating a revert PR. The warning also notes: "If `dev` must work before the revert PR is merged, ask in the team channel."

## after a manual knowledge base sync (2026-10-20T09:35:16+00:00)

| Agent | Suggests `gh run rerun` | Says not to re-run | Mentions revert |
|---|---|---|---|
| copy | yes | no | yes |
| managed KB | no | yes | yes |
| team-docs | no | yes | yes |

**copy**

According to the Roll back a bad deploy on dev runbook, the quickest way is the **fast path: redeploy the last good commit**.

Use these commands:

```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

Find the run of the last good commit and re-run it. This deploys that run's commit again without needing to make code changes.

**Important:** This only changes what is deployed—the `dev` branch still has the bad commit. You must follow step 3 immediately after to revert the commit in a PR, otherwise the next merge will deploy the bad code again.

**managed KB**

According to the docs, the quickest way is to **create a revert PR**. Here's why:

The team stopped re-running old deploy-dev runs on 2026-10-20 because redeployed commits only last until the next merge, which deploys the bad commit again. So that's no longer the fast path.

Instead, follow these steps from page [1]:

1. Find the bad commit using `git switch dev && git pull --ff-only` and `git log --oneline -5`
2. Create a revert PR with `git switch -c` to a new branch, `git revert --no-edit <bad-commit-sha>`, amend the commit message with your ticket key, and push it
3. Open the PR with type bugfix and an expected behavior block
4. pr-triage reviews it like any other PR, and when merged, deploy-dev automatically deploys the reverted code

This is the only reliable way back. If dev must work before the revert PR is merged, ask in the team channel.

**team-docs**

According to the docs on rolling back a bad deploy on dev, the quickest way is to use the revert PR. The docs explicitly state:

> Re-running an old `deploy-dev` run used to be the fast path. The team stopped on 2026-10-20: the redeployed commit only lasts until the next merge, which deploys the bad commit again. Go straight to step 3. The revert PR is the only way back.

So you should skip re-running old deploys and go straight to creating a revert PR. The warning also emphasizes: "Do not re-run old `deploy-dev` runs."

(From page [1] "Roll back a bad deploy on dev > 2. Do not re-run old deploys", version 2, edited 2026-10-20 09:24 UTC)

## sync stopped for over 30 minutes (2026-10-20T10:23:00+00:00)

| Agent | Suggests `gh run rerun` | Says not to re-run | Mentions revert |
|---|---|---|---|
| copy | yes | no | yes |
| team-docs | yes | no | no |

**copy**

According to the Roll back a bad deploy on dev runbook, the quickest way is the **fast path: redeploy the last good commit**.

Use these commands:

```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

Find the run of the last good commit and re-run it. This deploys that run's commit again without needing to make code changes.

**Important:** This only changes what is deployed—the `dev` branch still has the bad commit. You must follow step 3 immediately after to revert the commit in a PR, otherwise the next merge will deploy the bad code again.

**team-docs**

Based on page [1] "Roll back a bad deploy on dev > 2. Fast path: redeploy the last good commit", the quickest way is:

1. Find the last good commit's deploy run:
```bash
gh run list --workflow deploy-dev --repo jaeneungsim/demo-inventory-api --limit 10
```

2. Re-run that deployment:
```bash
gh run rerun <run-id> --repo jaeneungsim/demo-inventory-api
```

This redeploys the last good commit immediately. However, the warning notes that this only changes what's deployed—the `dev` branch still has the bad commit, so the next merge will deploy it again. You'll need to follow step 3 after this (which would be fixing or reverting the bad commit on the `dev` branch, as described in the full rollback page [5]).
