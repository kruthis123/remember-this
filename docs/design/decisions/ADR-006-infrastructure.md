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

## Amendment (step 10, implementation time) — Cloud Run swapped for AWS Lambda

Cloud Run requires a billing account linked to the GCP project even to stay within its free tier, and
setting one up was declined. AWS App Runner — the direct Cloud Run equivalent considered here — stopped
accepting new customers as of April 30, 2026, so it was not an available substitute either. The only
remaining scale-to-zero, webhook-native, always-free option was AWS Lambda, which this project now uses
in place of Cloud Run. Everything else this ADR decided — webhook transport, Neon Postgres, one bot
token, no backups, the whole turn processed inside the request — is unchanged.

The swap is bigger than a hosting-provider substitution: Lambda does not run an arbitrary web server, so
`remember_this/bot/webhook.py` changed from a FastAPI app to a Lambda handler function invoked via a
Lambda Function URL (Lambda's equivalent of a public HTTPS endpoint, chosen over API Gateway since no
routing, auth, or request transformation beyond what the handler already does is needed). The handler is
necessarily synchronous at the top level — Lambda does not support `async def` handlers — so it owns one
persistent `asyncio` event loop at module scope, reused across warm invocations, since `asyncpg`'s
connection pool is bound to the loop that created it and a fresh loop per invocation would leave the pool
unusable after the first call. `handlers.py`, `command.py`, `telegram_client.py`, and `keyboards.py` were
unaffected — they only ever depended on a plain `dict` update, never on FastAPI.

Packaging also changed from "any image Cloud Run will run" to a Lambda-specific container built from
`public.ecr.aws/lambda/python:3.12`, since this project's dependencies (`asyncpg`'s compiled extension,
`pydantic-ai`, `langfuse`) are too large and too platform-specific for Lambda's 250MB zip-upload path.

This is recorded as an amendment rather than a full ADR rewrite because the reasoning that chose a
scale-to-zero webhook host in the first place is untouched; only which specific provider satisfies that
reasoning changed, and only because of an availability constraint (App Runner) and a cost-of-entry
constraint (GCP billing) neither anticipated when this ADR was first written.

### Consequences of the amendment

Easy: AWS Lambda's always-free tier (1M requests + 400,000 GB-seconds/month) comfortably covers this
bot's traffic with no billing account required to get started. ECR's free tier covers the one image this
project needs.

Hard: the FastAPI-to-Lambda-handler rewrite is new surface that did not exist when this ADR was written,
and it is AWS-specific in a way the original Cloud Run plan was not — moving hosts again would mean
touching `webhook.py` again, not just redeploying. Lambda's own cold start (observed ~5.7s container init
plus Neon's own wake time on the very first request) has not yet been formally separated from warm-path
latency the way the "How this will be measured" section below commits to; that measurement is still
owed.

### Revisit trigger (amendment)

- AWS Lambda's free tier changes materially, or GCP billing friction is resolved and Cloud Run becomes
  simpler to pick up again.
- The synchronous-handler-plus-persistent-event-loop pattern in `webhook.py` causes a hard-to-diagnose
  bug under real concurrent traffic (Lambda can run multiple concurrent instances of the same function,
  each with its own loop and pool — this has not yet been tested under concurrent invocations).
