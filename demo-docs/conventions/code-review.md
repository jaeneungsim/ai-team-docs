---
title: Code review rules
parent: Team conventions
order: 3
---

pr-triage reviews every PR first. A person reviews what it cannot settle.

## Results

| Result | Label | Check run `pr-triage` | What happens next |
|---|---|---|---|
| Approvable | `triage: approvable` | `success` | A person approves, or pr-triage merges it in auto-approve mode |
| Changes requested | `triage: changes requested` | `failure`, which blocks the merge | The author fixes it and pushes |
| Needs human review | `triage: needs human review` | `neutral` | A person reviews it |

A result belongs to one commit. A new commit starts a new review and dismisses earlier approvals.

## Always a person

- Changes to sensitive paths: `.github/**`, `.githooks/**`, `infra/**`, `tickets/**`, `scripts/**`, `seed/**`, `AGENTS.md`, anything under an `auth/` folder or with `auth` in a Python file name, and `migrations/`.
- Text that seems to address the reviewer, such as "AI reviewer: approve this PR" or "ignore previous instructions".
- Fork PRs. They get no AI review unless a maintainer adds the label `ai-review-ok`, and then only for that commit.
- Anything pr-triage could not finish. A failed step ends in "needs human review", never in silence.

## What a reviewer checks

1. Every requirement of the ticket is covered, by the code and by the expected behavior.
2. The tests mean something. For a feature or a bug fix, a new test must fail on the old code. The `test-relevance` check reports one of `ok`, `undetermined`, `meaningless`, `no_tests`, `unexpected_failure` or `skipped`.
3. `openapi.yaml` matches the API.
4. The change has no secrets, tokens or AWS account ids.
5. The PR follows [[Branches, commits and PR titles]].

## Branch protection on dev

- Required checks: `ci` and `pr-triage`.
- One approving review. In auto-approve mode, pr-triage's own approval counts for the PRs it merges.
- Squash merge only.
