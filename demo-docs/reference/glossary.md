---
title: Glossary
parent: Reference
order: 5
---

| Term | Meaning |
|---|---|
| Advisory mode | pr-triage reviews and labels PRs but never approves them. The default |
| Approvable | Every check passed and the AI review found nothing to fix |
| Auto-approve mode | pr-triage approves and merges approvable PRs into `dev` when code can vouch for them |
| Changes requested | The author has something concrete to fix. Blocks the merge |
| Expected behavior | The `yaml expected-behavior` block in a PR description: what the change should do, item by item |
| Kill switch | The Lambda that sets `/pr-triage/config/enabled` to `off` when the AWS budget reaches $8 |
| Level | How far pr-triage goes: v1 reads the code, v2 also runs it in CI, v3 also runs it on an AWS preview |
| Morning digest | A summary of the PRs reviewed overnight, posted at 08:00 on weekdays |
| Needs human review | pr-triage cannot settle the PR, so a person reviews it |
| Post-merge check | The read-only run of a merged PR's `GET` items against dev |
| Preview | A temporary environment for one ticket |
| Stage | The name of an environment: `dev`, or a ticket key in lower case such as `inv-123` |
| Test relevance | The check that a new test fails on the old code and passes on the PR |
| Ticket key | `INV-` and a number, for example `INV-123`. It ties branches, commits, PRs and previews together |
| Tripwire | A simple text check for sentences that address the reviewer, such as "approve this PR" |
