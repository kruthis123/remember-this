# ADR-006 — Webhook on Cloud Run, Neon Postgres with pgvector

- **Phase:** 5 — Storage, deployment, and infrastructure topology
- **Date:** 2026-09-17
- **Status:** accepted

## Context

A handful of family users, tens of messages a day, hundreds of memories each. Everything must sit inside a
free tier. A vector index is a study goal (ADR-004). Latency is free (ADR-001). Extraction is synchronous
because the reply confirms what was stored (ADR-003).

## Options considered

### Transport
**Long polling** needs an always-on process, which rules out every scale-to-zero host and therefore every
remaining free tier. **Webhook** chosen: no always-on process, at the cost of a public URL, a dev tunnel,
and cold starts.

### Compute
**Cloud Run** chosen — scale-to-zero, webhook-native, generous free request allowance. **Render free**
rejected: sleeps on idle with a worse cold start. **Fly.io / Railway** rejected: no meaningful free tier
remains in 2026. **Home machine or Pi** rejected: uptime becomes a personal problem and it demonstrates
nothing to a reader.

### Datastore
**Neon Postgres + pgvector** chosen: one store for relational and vector data, idle compute suspends and
wakes sub-second. **Supabase free** rejected: projects pause after a week of inactivity and need manual
restore, which is a likely failure for a bot used a few times a week. **SQLite + vector extension**
rejected: needs a persistent disk, contradicting scale-to-zero.

### Bot tokens
One token, accepting that local development temporarily takes the production webhook offline. Mitigated by
the eval harness exercising the agent directly rather than through Telegram.

### Backups
None. Loss accepted for v1.

## Decision

Telegram webhook into a Cloud Run service scaling to zero. Neon Postgres with pgvector as the single
datastore. One bot token. No backups. All secrets and all tuning parameters (thresholds, model, prompt
version) as injected configuration, surfaced in traces. The whole turn is processed inside the webhook
request, returning 200 at the end, with mandatory idempotency on Telegram's `update_id`.

## Why

The transport decision drove everything else — polling and free hosting are incompatible in 2026, so
webhook was effectively forced once cost was a constraint. Cloud Run and Neon both suspend when idle, which
suits a bot that receives a handful of messages a day, and their cold starts are affordable precisely
because Phase 0 refused to trade correctness for latency.

Choosing Neon over Supabase came down to one operational detail rather than features: a paused project that
needs manual restore would take the bot down silently between uses, which is the worst failure mode for
something family members rely on.

## Consequences

Easy: zero expected cost; one datastore to operate; no always-on process to babysit.

Hard: two suspended components stack on the first message after idle, so cold and warm latency must be
reported separately or the latency numbers are meaningless. Because CPU is only guaranteed during the
request, the whole turn runs inside it, so turn duration is bounded by Telegram's patience rather than by
anything internal — an unusually slow turn can trigger a retry that idempotency then absorbs. Duplicate
delivery would otherwise silently double-store facts, making `update_id` idempotency a correctness
requirement rather than hygiene. A single bot token makes local development mutually
exclusive with production being up.

Foreclosed: nothing significant. Every one of these is cheaply reversible.

## How this will be measured

Cold vs warm end-to-end latency, reported separately. Database latency isolated from LLM latency. Duplicate
update rate. Monthly cost, expected to be zero.

## Revisit trigger

- Cold starts become annoying in real family use — pay for a warm instance, or reconsider polling on a
  cheap always-on host.
- Local development friction from the single token becomes a drag — add a second bot token.
- Family members lose memories they cared about — backups stop being optional.
