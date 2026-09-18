# Phase 6 — Observability

Status: decided. Decision record: `decisions/ADR-007-observability.md`.

Goal, stated as a requirement rather than an aspiration: when a family member says "it gave me a wrong
answer", the cause is identifiable from a single trace in a few minutes.

## Platform

**Langfuse Cloud, Hobby tier.** One destination for everything — development, eval runs, and production.

Self-hosting was considered and rejected on practicality: Langfuse v3 runs six containers (web, worker,
Postgres, ClickHouse, Redis, MinIO) and its own guidance points at roughly 4 cores and 16 GB for a real
deployment. Viable on a laptop, not on any free tier, and not worth a weekend.

Hobby-tier limits to design within: a monthly quota counted in billable units (traces plus observations
plus scores) and roughly a month of data retention. Two consequences: verbose tracing consumes quota
faster than expected, and long-term trend analysis is not available — anything worth keeping must be
exported into the eval dataset rather than left in the platform.

Note that Langfuse offers grants for research and education use, which may apply given the university
context.

## Instrumentation

OpenTelemetry-based, via Pydantic AI's emitted spans plus manual spans for what the framework does not
know about (retrieval, database access, Telegram handling). Langfuse receives OTel data, so the exit cost
to another backend stays low.

## Trace model

One **trace per Telegram update**. Spans within it:

| Span | Key attributes |
|---|---|
| turn | hashed user id, `update_id`, cold/warm, intent (tool chosen), outcome, total latency, total tokens |
| agent step | model, prompt version, tool chosen, token counts, latency |
| extraction | raw message, extracted facts, fact count, schema valid |
| retrieval (per pass) | query text, embedding model, candidate memory ids with similarity scores including rejected ones, threshold in force, pass number |
| relevance check | candidates considered, verdict, stated reasoning |
| answer generation | retrieved facts used, answer text, cited memory ids, abstention flag |
| database | operation, latency |

Outcome values worth distinguishing: answered, abstained, clarification requested, unclassifiable,
duplicate update skipped, error.

## Payloads and privacy

**Full payloads.** Prompts, completions, raw messages, and memory text are stored unredacted. Anything
less makes the debugging requirement above unachievable.

**Hashed user ids.** Telegram user ids are hashed before leaving the service, so traces are not linkable
to a person from inside Langfuse. Costs nothing.

**Disclosure over withholding.** `constraints.md` C6 is satisfied by telling users plainly rather than by
crippling the traces. `/start` and `/help` state: messages and answers are stored in a third-party
observability tool for about a month to diagnose problems, and `/forget` deletes stored memories.

**`/forget` does not purge traces, and `/help` says so.** Selective trace deletion is not available on the
Hobby tier. `/help` states that `/forget` deletes stored memories, and that diagnostic traces of past
conversations age out on their own within about a month. Stating the limitation is preferable to implying a
completeness the system cannot deliver.

## User feedback

Thumbs up / down buttons on every answer, attached as a score on the trace. The cheapest route from real
usage to eval data: a thumbs-down is a labelled failure with a full trace already attached, which is
exactly what Phase 7's dataset should grow from.

Implicit signal worth capturing too: the same question asked again shortly after an answer usually means
the answer was bad.

## Metrics to watch on the dashboard

No alerting in v1 — the dashboard is checked when something feels wrong. Worth having visible:

- fabrication and false-abstention indicators, from thumbs-down and eval runs
- abstention rate and clarification rate
- retrieval hit rate at strict threshold, and how often the relaxed retry rescues a turn
- cold vs warm latency, separately
- tokens per turn
- schema validation failures, duplicate updates, errors

## The loop this exists to enable

trace → thumbs-down or manual review → case added to the eval dataset → prompt or threshold change →
eval run → deploy → new traces.

That loop is the portfolio artifact. The bot is the excuse for it.
