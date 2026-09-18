# Phase 5 — Storage, deployment, and infrastructure topology

Status: decided. Decision record: `decisions/ADR-006-infrastructure.md`.

## Topology

```
Telegram  --webhook HTTPS-->  Cloud Run service (scale to zero)
                                   |
                                   +--> university LLM / embedding endpoints
                                   +--> Neon Postgres + pgvector
                                   +--> observability backend (Phase 6)
```

## Locked decisions

**Webhook, not polling.** Enables scale-to-zero and needs no always-on process. Costs a cold start on
the first message after idle, and a tunnel for local development.

**Google Cloud Run.** Scale-to-zero container with a generous free request allowance, and webhook-native.
Rejected: Render free (sleeps, and its cold start is worse), Fly.io and Railway (no meaningful free tier
in 2026), a home machine (uptime is your problem and it is invisible to a reader of the repo).

**Neon Postgres with pgvector.** One datastore for both relational records and vectors. Compute suspends
when idle and wakes in well under a second, which composes acceptably with a scale-to-zero service.
Rejected: Supabase free, which pauses projects after 7 days of inactivity and needs manual restore — a
real hazard for a bot used a few times a week. Rejected: SQLite plus a vector extension, which would tie
the service to a persistent disk and contradict scale-to-zero.

**One bot token.** No separate dev bot. See the friction note below.

**No backups.** Memory loss is acceptable in v1. Recorded as an accepted risk, not an oversight.

## Cold start reality

Two suspended things sit in the path of the first message after an idle period: the Cloud Run instance
and the Neon compute. Both wake quickly, but they stack, and they land on top of synchronous LLM
extraction. Phase 0 declared latency free, so this is acceptable — but it should be *measured* per Phase 6
rather than assumed fine, and cold vs warm latency reported separately or the numbers will be
meaningless.

## Webhook handling

**Process fully inside the request; return 200 at the end.** CPU stays allocated for the whole turn, which
is what Cloud Run guarantees during a request and not after it.

**Idempotency on Telegram's `update_id` is mandatory.** Telegram retries updates it does not see acked, and
a retry that re-runs extraction would store the same fact twice and silently corrupt the memory store.
Recording seen `update_id`s makes a retry a no-op.

Rejected: ack immediately and process in the background with CPU-always-allocated (removes timeout risk but
defeats scale-to-zero, the reason Cloud Run was chosen); ack and enqueue to a second consumer (correct at
scale, absurd for five users).

Residual risk: an unusually slow turn — cold start plus extraction plus a relaxed-threshold retry — could
outlast Telegram's patience and trigger a retry that the idempotency check then absorbs. The user sees
nothing wrong, but the trace will show it, which is why turn duration and duplicate rate are both logged.

## Local development

One bot token means Telegram will only hold one webhook target at a time, so pointing it at a local
tunnel takes production offline until it is pointed back. Two mitigations that make this tolerable:

- The eval harness (Phase 7) exercises the agent directly, not through Telegram, so the great majority of
  iteration never touches the bot API at all.
- Local runs can use polling with the webhook temporarily removed, accepting that production is down
  meanwhile.

If this friction bites, a second bot token is free and the decision is trivially reversible.

## Configuration and secrets

- Bot token, LLM endpoint and key, database URL, observability key: environment variables, injected by
  Cloud Run, never committed.
- Thresholds (strict and relaxed), model identity, and prompt version are configuration too — they must be
  visible in traces so a run can be reproduced.

## Scale and cost budget

- Users: a handful. Messages: tens per day at most.
- Memories: hundreds per user, a few KB each. Comfortably inside Neon's free storage.
- Cloud Run requests: far below the free allowance.
- LLM and embedding calls: free via university endpoints; rate limits are the constraint, not price.
- Expected monthly cost: zero. If it is not zero, something is misconfigured.

## What must be logged for Phase 6

- cold start vs warm, as a trace attribute
- `update_id`, and whether the update was a duplicate that was skipped
- database query latency separately from LLM latency
- the config in force: thresholds, model, prompt version
