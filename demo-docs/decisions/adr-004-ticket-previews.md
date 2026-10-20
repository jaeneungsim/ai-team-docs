---
title: ADR-004 Previews per ticket, not per PR
parent: Decisions
order: 4
---

{status:Accepted|Green} · Decided 2026-10-11

## Context

One ticket often needs a PR in the API repo and another in the web repo. A preview of a single PR cannot show that the two work together.

## Decision

Each ticket gets one preview, named after the ticket key in lower case. This name is the stage, for example `inv-123`.

- API: a stack `inv-api-preview-inv-123` with its own function, table and log group.
- Web: the prefix `/inv-123/` in one shared bucket behind one CloudFront distribution. Its `config.js` points at the ticket's API stack when that stack exists, and at the dev API otherwise.

A preview is removed when the PR closes. As a backstop, an hourly job removes previews that are older than 24 hours or have no open PR.

## Why a prefix for the web, not a stack

Creating or deleting a CloudFront distribution takes minutes. Copying files to a prefix takes seconds and needs no CloudFront permissions in the preview roles.

## Consequences

- Previews run in the same AWS account as `dev`. Three layers keep them contained:
  - deploy roles that trust one repo and one event each;
  - one CloudFormation role, `inv-preview-cfn-exec`, that can only create what the app uses;
  - the permissions boundary `inv-preview-boundary` on every role the app creates.
- For a real organization, a separate preview account is still the stronger choice.
- Fork PRs never get a preview.
