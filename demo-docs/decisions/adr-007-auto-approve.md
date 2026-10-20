---
title: ADR-007 Advisory mode by default, auto-approve only when code can vouch
parent: Decisions
order: 7
---

{status:Accepted|Green} · Decided 2026-10-12 · Discussed in [[2026-10-12 Review process check-in]]

## Context

AI coding agents open several PRs a day, many of them outside working hours. In advisory mode every PR waits for a person even when every check has passed, so overnight PRs wait until the next morning.

## Decision

pr-triage has two modes, set in the SSM parameter `/pr-triage/config/mode`:

- `advisory`, the default: pr-triage reviews and labels, but never approves. A person approves and merges.
- `auto-approve`: pr-triage approves an approvable PR into `dev` and squash-merges it, but only when code can vouch for it.

Code can vouch for a PR in one of two cases:

- The PR changes only docs, or only tests.
- The PR changes code, and all of these hold:
  - its expected behavior actually ran and passed, in CI from level v2 and on the AWS preview at v3;
  - its new tests fail on the old code;
  - its ticket lives in this repo alone;
  - it has no `ui` items for a person to look at.

Everything else waits for a person. Nothing is promoted beyond `dev` automatically.

## Consequences

- The merge names the reviewed commit SHA, so GitHub refuses it if a newer commit arrived.
- The GitHub App needs contents write access, and its approval counts as the one required review.
- To go back to advisory mode, see [[Review a PR again or change the review level]].
