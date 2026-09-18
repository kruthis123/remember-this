# ADR-009 — Open access with rate limits, app-level isolation, injection treated as data

- **Phase:** 8 — Multi-tenancy, safety, and failure behaviour
- **Date:** 2026-09-17
- **Status:** accepted

## Context

DM-only, a handful of intended users, LLM access via university quota rather than a paid account. The whole turn
runs inside a webhook request with no retries budgeted (ADR-006). Fabrication is a release-gating failure
(ADR-001).

## Options considered

### Access
**Allowlist** would remove the abuse question entirely but adds friction to sharing the bot with family and
teaches nothing.
**Open with usage visibility and rate limits** chosen — abuse becomes detectable and gating stays a config
change away.

### Isolation
**App-level filtering** chosen. **Postgres row-level security as a second layer** rejected for v1: real defence
in depth, but the realistic failure here is a forgotten filter in a query, which a required-argument convention
and a cross-user eval case catch more directly.

### Prompt injection
**Ignore as a documented limitation** rejected: the outcome is a fabricated answer, which is gated.
**Sanitisation or a classifier** rejected: disproportionate and unreliable.
**Structural handling** chosen — memories passed as structured data rather than prose, a system prompt that
treats memory content as data, mandatory citation, and injection cases in the eval set.

### Infrastructure failures
**Retry then apologise** rejected: the turn runs inside the webhook request and the retry budget is already
spent on the relaxed search pass.
**Fail fast with a clear message** chosen.

### Input validation
**Store whatever comes** chosen. No length or junk filtering.

## Decision

Open bot with per-user rate limits counted in Postgres, and a usage dashboard to detect abuse. Application-level
isolation with user id as a required argument on every read and write, plus a cross-user eval case. Prompt
injection handled structurally (memories as data, citation required, injection cases evaluated), not by
sanitisation. Infrastructure failures fail fast with specific, clear messages and no retries. All handled errors
still return 200 to Telegram. `/forget` deletes memories; traces are not purged and `/help` says so.

## Why

Rate limiting is what makes openness defensible: it bounds a stranger's consumption of a shared university quota
to something noticeable-but-harmless before the dashboard reveals them. Without it, open access would be
delegating quota control to good manners.

Injection is worth handling not because family members are adversaries but because the failure mode it produces
is precisely the one Phase 0 refuses to tolerate. The measures chosen are structural and free, which is the right
size of response — and they are honestly described as risk reduction rather than prevention.

Failing fast follows from the webhook-bound turn: a retry inside the request competes with Telegram's patience,
and a slow failure is worse than a fast, clearly worded one.

## Consequences

Easy: sharing the bot is frictionless; gating is a config change; injection defences cost nothing and are measured
rather than assumed.

Hard: an open bot means unknown users' personal content in traces, disclosed via `/help` that strangers will not
read. Hashed trace ids mean the observability tool alone cannot identify who to block — the application database
is the source of truth for that, which needs to be known before an incident rather than during one. App-only
isolation means a single forgotten filter is a cross-user leak, the highest-severity bug available here. Storing
whatever comes leaves a long-message token-consumption path open, visible in logs but unbounded.

Foreclosed: nothing. Allowlisting, RLS, and input limits are all additive later.

## How this will be measured

Distinct users and per-user message volume on the dashboard. Rate-limit hit rate. Cross-user isolation eval case,
which must pass on every run. Injection eval category, scored for faithfulness. Error rates by failure type.

## Revisit trigger

- Unknown users appear in volume — switch to an allowlist.
- A cross-user leak occurs or nearly occurs — add row-level security.
- Long-message token consumption becomes material against the university quota — add a length limit.
