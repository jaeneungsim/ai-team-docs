---
title: 2026-10-12 Review process check-in
parent: Inventory Team
order: 6
---

**Date:** 2026-10-12 · **Attendees:** app owner, reviewer

## Notes

- Overnight PRs still wait for a person in advisory mode, even when every check passed. The reviewer said most of those PRs needed no change.
- We agreed to try auto-approve mode for PRs into `dev`, limited to PRs that code can vouch for. Written up as [[ADR-007 Advisory mode by default, auto-approve only when code can vouch]].
- First run in auto-approve mode: the pr-triage bot approved and merged the INV-124 fix PR 112 seconds after the push. The post-merge check on dev passed, and the preview was removed.
- The INV-125 PR with text addressed to the AI reviewer stayed "needs human review". The tripwire caught it in about 11 seconds, without calling the model.
- Kill switch test: a test message to the budget stop topic switched reviews off in 6 seconds. We switched them back on straight away.

## Decisions

- Mode is `auto-approve` from today. Promotion beyond `dev` stays with people.

## Actions

- [x] Write ADR-007.
- [x] Write the runbook [[Turn AI reviews back on after a budget stop]].
- [ ] Switch the web detail page from `stock` to `sold_out`. Needs a ticket.
- [ ] Revisit the model when Claude Haiku 5.5 is enabled for the account.
