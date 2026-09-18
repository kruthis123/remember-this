# ADR-007 — Langfuse Cloud, full payloads, hashed user ids, feedback buttons

- **Phase:** 6 — Observability
- **Date:** 2026-09-17
- **Status:** accepted

## Context

LLM observability is a primary learning goal, not a supporting concern. Traces will contain family members'
personal notes. `constraints.md` C6 asks for privacy to be considered without over-engineering. Pydantic AI
emits OpenTelemetry spans (ADR-005). Everything must be free.

## Options considered

### Platform
**Langfuse Cloud Hobby** chosen: tracing, prompt management, datasets, and evals in one product, free tier
sufficient at tens of messages a day, OTel-compatible ingest.
**Self-hosted Langfuse** rejected on practicality: v3 needs six containers and guidance points at roughly
4 cores and 16 GB, which no free tier provides.
**Phoenix** and **Opik** were credible alternatives; Langfuse won on breadth of features in one place.

### Scope of tracing
**Production tracing off, dev only** was considered and rejected. It would remove the ability to diagnose a
real complaint, leave the feedback buttons with nothing to attach to, and break the trace-to-dataset loop —
the three things the phase exists for.

### Payloads
**Full, unredacted** chosen. **Redacted or hashed content** rejected: it would make the stated debugging
requirement unachievable, which is too high a price at five trusted users.

### Identity
**Hashed Telegram user ids** chosen. Free, and makes traces unlinkable to a person from inside the platform.

## Decision

Langfuse Cloud Hobby as the single destination for dev, eval, and production. OTel-based instrumentation.
One trace per Telegram update, with spans for the agent step, extraction, each retrieval pass, the relevance
check, answer generation, and database access. Full payloads. Hashed user ids. Thumbs up/down buttons on
answers, recorded as trace scores. No alerting; dashboard reviewed on demand. Privacy handled by disclosure
in `/start` and `/help`.

## Why

The privacy tension resolved toward disclosure rather than redaction because the alternative defeats the
purpose of the phase, and because at this scale the users are family who can be told plainly what happens
to their data. Hashing ids is the part of the privacy posture that costs nothing, so it is not a tradeoff at
all.

Keeping tracing on in production is what makes the feedback buttons and the eval-dataset growth loop
possible; turning it off would have left a development-time debugging tool and called it observability.

## Consequences

Easy: one trace per turn with everything needed to explain any answer; thumbs-down produces a labelled
failure with full context attached, which is the cheapest possible eval dataset growth.

Hard: Hobby quota is counted in traces plus observations plus scores, so verbose spans consume it faster
than expected — span granularity is a budget decision, not just a design one. Retention is about a month,
so anything worth keeping must be exported into the eval dataset rather than left in the platform. Personal
content lives in a third-party service, mitigated by disclosure rather than eliminated. `/forget` deletes
memories but cannot purge traces on this tier; `/help` states this outright rather than implying a
completeness the system cannot deliver.

## How this will be measured

Time to diagnose a real reported failure from its trace — the phase's actual success criterion. Quota
consumption against the monthly allowance. Feedback volume and thumbs-down rate.

## Revisit trigger

- Hobby quota is exhausted before month end — reduce span granularity or sample.
- A family member objects to third-party storage — reopen the redaction decision.
- Retention becomes limiting for trend analysis — export traces on a schedule, or self-host on paid infra.
