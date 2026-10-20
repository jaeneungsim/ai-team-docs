---
title: ADR-008 Claude Haiku 4.5 through the Australian inference profile
parent: Decisions
order: 8
---

{status:Accepted|Green} · Decided 2026-10-11

## Decision

The AI review step calls Claude Haiku 4.5 on Amazon Bedrock through the Australian cross-region inference profile `au.anthropic.claude-haiku-4-5-20251001-v1:0`.

- Requests stay in Australian regions.
- Price: $1.10 per million input tokens and $5.50 per million output tokens. A typical review costs about 2 cents.
- The model must answer with one forced tool call, `submit_review`, so the answer always has the same JSON shape.
- Limits per call: 30,000 input tokens and 3,000 output tokens. A PR that needs more goes to a person without an AI review.

The model id and its prices are settings: `infra/cdk.json` in pr-triage, deployed to the SSM parameter `/pr-triage/config/model`. Changing the model needs no code change.

## Why not a bigger model

The review only suggests; code decides. A small model keeps a review at a few cents, and any doubt still goes to a person.

## Revisit when

Claude Haiku 5.5 is enabled for our account. On 2026-10-11 it was listed but not yet usable, so we stayed on Haiku 4.5.
