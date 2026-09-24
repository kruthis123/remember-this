# Step 7 — Observability

Files you will write: `remember_this/observability/tracing.py`, plus small additions to
`retrieval/search.py`, `agent/tools.py`, `agent/agent.py`, and `db/repository.py` to emit spans/attributes
at the points `phase-6-observability.md`'s trace model requires.

Design references: ADR-007 and `phase-6-observability.md` (the trace model, span table, and privacy
posture — read the whole doc again, this step implements it literally), `constraints.md` C6 (the privacy
tension already resolved as disclosure over redaction, so this step stores full payloads by design).

There is no user-facing behavior change in this step. Everything built in steps 3–6 keeps working exactly
as it does now; this step makes what it's doing *visible*. Treat that as the actual goal: if you finish
this step and cannot diagnose a wrong answer from a trace in a few minutes, per the doc's own stated
success criterion, the step isn't done regardless of how much instrumentation code exists.

---

## Part 0 — Concepts you need first

### What Langfuse actually is, mechanically

Langfuse ingests OpenTelemetry (OTel) trace data. A **trace** is one logical unit of work (here: one
Telegram update, per the design doc). A **span** is one step within it, with a start/end time, attributes
(key-value metadata), and optionally its own child spans, nested arbitrarily deep. Langfuse's UI groups
everything under one trace and lets you expand into its spans — this is what makes "look at one trace, find
the cause" possible at all.

Two ways to get spans into Langfuse for this project, and you'll likely use both:

- **Automatic, from Pydantic AI.** Pydantic AI has built-in OpenTelemetry instrumentation — every
  `agent.run()` call and its internal LLM calls/tool calls can emit spans on their own, if instrumentation
  is enabled. Look up how Pydantic AI's OTel integration is turned on (there is usually a single
  configuration call or environment variable that activates it) and what it captures by default (model
  name, prompt, completion, token counts are typical). This alone likely covers a large fraction of the
  "agent step" row in the trace-model table.
- **Manual spans, for everything Pydantic AI doesn't know about.** Retrieval passes, the relevance check's
  reasoning, database calls, and Telegram-specific handling (not yet built, but plan for it) are not inside
  Pydantic AI's world — you create spans for these yourself. Look up the OpenTelemetry Python SDK's tracer
  API: getting a tracer, starting a span (often as a context manager), and setting attributes on it.

### Getting Langfuse to receive the data

Langfuse Cloud accepts OTel data via an OTLP endpoint, authenticated with the public/secret key pair you
already have in config (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`). Look up Langfuse's
current OTel setup docs for the exact exporter configuration — this is the kind of integration detail
worth reading fresh rather than guessing, since SDK setup shapes change between versions. The likely shape:
configure an OTel `TracerProvider` with an OTLP exporter pointed at Langfuse's endpoint, with the keys
encoded into the request per Langfuse's auth scheme (commonly HTTP Basic Auth using the two keys). Do this
once, at process startup, in `observability/tracing.py`, and have every other module obtain a tracer from
the standard OTel API rather than importing anything Langfuse-specific — this is what ADR-005/ADR-007 mean
by staying OTel-native rather than coupling to one vendor's SDK.

### The hashing requirement is not optional plumbing

ADR-007 and `phase-6-observability.md` are explicit: **hashed user ids, not raw Telegram ids**, in
anything that leaves the service. This has to happen at the point spans are created, not as an
afterthought — if a raw `user_id` ever gets set as a span attribute even once, it has already left your
service and the guarantee is broken. Write one small function,
`hash_user_id(user_id: int) -> str`, using `USER_ID_SALT` from config (HMAC or salted SHA-256 are both
fine choices — look up which one to use with `hmac`/`hashlib` and be deliberate about it), and make it the
**only** way a user id ever gets attached to a span anywhere in the codebase. Every span-creation call site
should go through it, never through the raw id directly.

---

## Part 1 — The trace model, and where each span actually gets created

Re-read the span table in `phase-6-observability.md` before writing code; here is where each one maps to
code that already exists:

| Span | Where in the code it belongs |
|---|---|
| turn | wraps the whole `agent.run(...)` call — this is the outermost span, and is likely where the trace itself starts. Needs: hashed user id, Telegram `update_id` (not available until step 9's webhook exists — for now, use a placeholder or the test script's own generated id), cold/warm (also step 9's concern; note the attribute now, populate it later), tool chosen, outcome, total latency, total tokens |
| agent step | likely comes largely for free from Pydantic AI's own instrumentation once enabled |
| extraction | inside `extract_facts` (step 3) or wrapping its call site in `save_memories` — needs raw message, extracted facts, fact count, schema-valid flag |
| retrieval (per pass) | inside `retrieve()` (step 4) — one span per search pass (strict, then relaxed if it happens), with query text, embedding model, candidate ids + similarity scores including rejected ones, threshold in force, pass number |
| relevance check | inside `check_relevance` (step 4) or wrapping its call site — candidates considered, verdict, reasoning |
| answer generation | inside `generate_answer` (step 5) or its call site — retrieved facts used, answer text, cited ids, abstention flag |
| database | inside `repository.py`'s functions, or wrapping calls to them — operation name, latency |

Decide, function by function: does the span get created *inside* the function itself (keeps instrumentation
close to the logic, but couples every function to tracing), or does the *caller* wrap the call in a span
(keeps the underlying functions trace-agnostic, but means every call site has to remember to do it)? Neither
is uniformly right — a reasonable split is: instrument inside the LLM-calling functions themselves (since
they're the things being measured, and there's exactly one call site of concern for most of them), and
instrument at the call site for `repository.py`'s DB functions (since they're called from many places and
you don't want a decision about tracing granularity baked into the lowest-level data layer).

### Outcome values

`phase-6-observability.md` lists: answered, abstained, clarification requested, unclassifiable, duplicate
update skipped, error. You don't have a clarification tool (step 6's documented deviation) or webhook-level
duplicate detection yet (step 9) — decide whether to record a placeholder/not-applicable value for those
now, or add the enum values only when the corresponding feature exists. Either is fine; be consistent.

---

## Part 2 — Attaching attributes without breaking privacy or leaking noise

### What "full payload" actually means here, and its limit

ADR-007 says full, unredacted payloads — prompts, completions, raw messages, memory text. This is a
deliberate choice already made; don't second-guess it into partial redaction. But "full payload" only ever
meant *content*, not *identity* — the raw message text belongs in a span; the raw Telegram user id never
does. Keep that line exact.

### Configuration attributes belong on every relevant span

Recall `config.py`'s `trace` property from step 1 — it exists precisely for this step. `phase-6-
observability.md` requires model identity, prompt version, and thresholds in force to be attached wherever
relevant, specifically so a run is reproducible from its trace alone. Use `settings.trace` (or the specific
fields it contains) rather than re-deriving these values ad hoc at each span — one property, many call
sites, no drift between them.

### Watch quota, don't guess it

Hobby tier bills traces + observations (spans) + scores as one quota. A verbosely-spanned turn — outer
turn span, agent step, extraction, two retrieval passes, relevance check, answer generation, several DB
spans — could be a dozen observations per turn. Run a handful of test turns through once tracing is wired
up, then actually look at Langfuse's usage dashboard to see what a turn costs in real units, rather than
assuming. This number should inform whether you need to drop or merge any spans before considering this
step done.

---

## Part 3 — Verifying this actually works, not just compiles

Verification for this step is different from every step before it: passing type checks and running without
exceptions is necessary but not sufficient. The actual test is **can you use it**.

1. Run a feed message and a question through the agent (reuse `scripts/test_agent_end_to_end.py`'s cases).
2. Open the Langfuse UI and find the resulting traces.
3. Pick one, and without looking at your own code, try to answer: what did the user ask, what tool was
   called, what did retrieval return and at what similarity, did the relevance check run and what did it
   decide, what was the final answer and its citations. If any of these require guessing or aren't visible
   at all, that attribute is missing and needs adding.
4. Deliberately trigger one of the two documented findings from step 6 (the Nobu-style borderline case, or
   the injection-flavored feed message) and confirm the trace shows *why* the system behaved the way it
   did — this is the realistic version of "diagnose a complaint from a trace," using bugs you already know
   about as the test case instead of a hypothetical one.

---

## Pitfalls

- A raw `user_id` reaching any span attribute, even once, defeats the hashing guarantee — audit every
  span-creation call site for this specifically, don't assume it's fine because most of them are careful.
- Don't let "full payload" bleed into re-litigating the privacy decision — that's already settled by
  ADR-007; this step implements it, doesn't reopen it.
- Verbose span creation can quietly burn Hobby-tier quota faster than expected — measure actual per-turn
  cost early, don't find out a month in.
- Passing without errors is not the bar. If a trace doesn't let you explain a specific answer without
  reading source code, the instrumentation is incomplete regardless of whether it "ran successfully."

## Done when

- A feed turn and a question turn each produce one trace in Langfuse with nested spans matching the table
  above (as populated so far — clarification/duplicate-update outcomes may be placeholders).
- No raw Telegram user id appears anywhere in a trace — confirm by grepping the actual span attributes sent,
  not just the code that constructs them.
- You can pick a trace at random and state, from the UI alone, what tool was called, what retrieval found
  and at what similarity, whether the relevance check ran and why, and what the final answer cited.
- You know, from checking the Langfuse dashboard after a batch of test turns, roughly how many observations
  one turn consumes.
- You can re-diagnose one of the two step-6 findings (the Nobu nondeterminism case, or the injection case)
  purely from its trace.
