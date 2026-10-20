---
title: Branches, commits and PR titles
parent: Team conventions
order: 1
---

Every change starts from a ticket in `demo-inventory-api/tickets/`, and the ticket key ties everything together.

| What | Format | Example |
|---|---|---|
| Ticket key | `INV-<number>`, upper case | `INV-123` |
| Branch | `INV-<number>-short-description` | `INV-123-stock-in-detail` |
| Commit message | `INV-<number>: what changed` | `INV-123: return stock in item responses` |
| PR title | `INV-<number> What changed` | `INV-123 Return stock in item responses` |
| Preview stage | the key in lower case | `inv-123` |

- pr-triage looks for the ticket key in the branch name first, then in the PR title.
- The commit-msg hook rejects a commit message without the key. Enable it once per clone with `scripts/setup-hooks.sh`.
- One ticket and one purpose per PR. When a ticket lists several repos under `repos`, each repo gets its own PR with the same key.
- PRs are squash-merged. The PR title and description become the merge commit, so write the title for the history, not for the reviewer.

## Size

Keep PRs small. pr-triage sends a PR with more than 2,000 changed lines or more than 50 changed files to a person without an AI review.
