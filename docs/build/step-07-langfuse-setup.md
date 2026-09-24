# Step 7 detail — configuring Langfuse: automatic Pydantic AI tracing + manual spans

Companion to `step-07-observability.md`, focused specifically on getting Langfuse receiving data at all,
then adding manual spans for everything Pydantic AI doesn't see. Read `step-07-observability.md` first for
the trace model (which spans should exist and what attributes they need) — this doc is about the mechanics
of actually emitting them.

---

## Part 0 — Bugs in the current `tracing.py`, fix these first

Your file currently:

```python
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", Settings.langfuse_public_key.get_secret_value())
os.environ.setdefault("LANGFUSE_SECRET_KEY", Settings.langfuse_secret_key.get_secret_value())
os.environ.setdefault("LANGFUSE_BASE_URL", Settings.langfuse_base_url)

Agent.instrument_all()
```

Two things missing, confirmed against Langfuse's own Pydantic AI integration guide
(https://langfuse.com/docs/opentelemetry/example-pydantic-ai):

1. **`get_client()` is never called.** Setting the env vars alone does nothing — `get_client()` is the
   call that actually reads them, authenticates, and registers the OTel span processor that ships spans to
   Langfuse. Without it, `Agent.instrument_all()` has nothing listening on the other end; spans are created
   locally and go nowhere.
2. **No verification and no flush hook.** The docs' own troubleshooting section names exactly these two as
   the most common causes of "traces aren't showing up" — worth building in from the start rather than
   discovering later.

Note also: env var name `LANGFUSE_BASE_URL` is correct (verified against the docs) — nothing wrong there.

---

## Part 1 — Fixing `tracing.py`

Rewrite it to do, in order: set env vars (as now), get and verify the client, enable instrumentation,
expose a flush function.

```python
import logging
import os

from langfuse import get_client
from pydantic_ai.agent import Agent

from remember_this.config import get_settings

_settings = get_settings()

os.environ.setdefault("LANGFUSE_PUBLIC_KEY", _settings.langfuse_public_key.get_secret_value())
os.environ.setdefault("LANGFUSE_SECRET_KEY", _settings.langfuse_secret_key.get_secret_value())
os.environ.setdefault("LANGFUSE_BASE_URL", _settings.langfuse_base_url)

_logger = logging.getLogger(__name__)

langfuse = get_client()

if not langfuse.auth_check():
    # Fail loudly rather than silently dropping every trace for the life of the process.
    raise RuntimeError(
        "Langfuse authentication failed -- check LANGFUSE_PUBLIC_KEY, "
        "LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL."
    )

Agent.instrument_all()


def flush() -> None:
    """Force-send any buffered spans. Call this at the end of any short-lived
    script or process (test scripts, CLI tools) -- the exporter batches and
    sends periodically, so a script that exits quickly can lose its traces
    without this. Not needed in a long-running server process, but harmless
    there either.
    """
    langfuse.flush()
```

Why `auth_check()` here and not left implicit: if your keys or host are wrong, you want the failure to be
"the process won't start" rather than "traces are silently absent," which is much harder to notice and
debug — the exact class of problem this whole phase exists to prevent elsewhere in the system.

### Wiring this into your existing scripts and the agent

Every entry point needs to import `remember_this.observability.tracing` **before** anything that creates a
Pydantic AI `Agent` runs — instrumentation has to be registered before agents are constructed, or spans
from an already-constructed agent may not be captured. In practice: import it near the top of
`remember_this/agent/agent.py`, before the `Agent(...)` construction, and call `tracing.flush()` at the end
of every test script in `scripts/` after `asyncio.run(main())`.

### The `instrument=True` question

Langfuse's own example passes `instrument=True` explicitly to `Agent(...)` even after calling
`Agent.instrument_all()`. Whether this is still necessary in your installed Pydantic AI version, or whether
`instrument_all()` alone now covers every agent instance created afterward, is worth checking directly
rather than assuming — check the installed `pydantic-ai` version's own docs/changelog for `instrument_all`.
If in doubt, add `instrument=True` to your `Agent(...)` call in `agent.py` anyway; it costs nothing to be
explicit and matches the last confirmed-working example.

---

## Part 2 — Verifying the wiring, before building manual spans on top of it

Do this before writing any manual span code — if automatic tracing isn't actually reaching Langfuse, manual
spans built on the same broken foundation won't either, and you'll be debugging the wrong layer.

1. Set `LANGFUSE_DEBUG=1` as an environment variable (per the docs' troubleshooting section).
2. Run one of your existing test scripts (`scripts/test_agent_end_to_end.py` is a good choice — it already
   exercises both tools).
3. Watch the debug log output for OTel spans being created and exported. Two distinct failure signatures to
   tell apart, per Langfuse's own troubleshooting guide:
   - spans appear in the debug log but never show up in the Langfuse UI → they're being created but not
     shipped; check `flush()` is being called, and double check the API keys/host.
   - no OTel spans in the debug log at all → instrumentation itself isn't active; check `instrument_all()`
     ran before the agent was constructed.
4. Once a run's spans show up in the Langfuse UI, unset `LANGFUSE_DEBUG` (it's verbose) and move to Part 3.

---

## Part 3 — Manual spans for what Pydantic AI doesn't instrument

Pydantic AI's automatic instrumentation covers the agent run and its LLM/tool calls. It knows nothing about
your retrieval passes, the relevance check's reasoning, or your database layer — those need manual spans, and
they need to nest correctly *inside* the automatically-created trace, not as separate unrelated traces.

### The core API: `start_as_current_span`

Langfuse's Python SDK (v3+, OTel-native) exposes span creation through the client object you already have
from `get_client()`. The pattern, as a context manager:

```python
from remember_this.observability.tracing import langfuse

with langfuse.start_as_current_span(name="retrieval.strict_pass") as span:
    matches = await search_memories(...)
    span.update(
        input={"query": question, "threshold": settings.strict_threshold},
        output={"match_count": len(matches), "matches": [m.fact_text for m in matches]},
    )
```

Key properties of this pattern worth understanding, not just copying:

- **"current span" nesting is automatic and context-local.** Because Python's `contextvars`-based OTel
  context tracks "what span is currently active," any span you start *inside* another `with
  start_as_current_span(...)` block automatically nests under it — you don't pass parent references
  manually. This is exactly why it needs to run inside the same async call stack as the agent run: if
  `retrieve()` is called from inside a tool, which is called from inside `agent.run()`, and Pydantic AI's
  instrumentation is what started the outer span, your manual span nests inside it for free.
- **`span.update(...)` (or similar — check the exact method name in your installed SDK version) is how you
  attach attributes.** Prefer structured `input`/`output` dicts over ad hoc string attributes where the SDK
  supports it — Langfuse's UI renders these specially (as readable JSON), which is directly useful for the
  "explain an answer from the trace alone" requirement.
- **The span closes automatically at the end of the `with` block**, capturing duration. You do not need to
  measure latency yourself.

### Where to put manual spans, mapped to the trace-model table

Following `step-07-observability.md`'s guidance on placement (instrument inside the LLM-calling functions
themselves, instrument at the call site for `repository.py`'s DB functions):

**Inside `retrieve()` (`retrieval/search.py`)** — one span per pass:

```python
with langfuse.start_as_current_span(name="retrieval.strict") as span:
    primary_candidates = await search_memories(user_id, question_embedding, settings.strict_threshold, ...)
    span.update(
        input={"threshold": settings.strict_threshold},
        output={"candidates": [{"id": m.id, "similarity": m.similarity} for m in primary_candidates]},
    )
```

Repeat for the relaxed pass. Attribute set per `phase-6-observability.md`'s table: query text, embedding
model, candidate ids with similarity scores **including rejected ones** (so don't filter the list down
before logging it — log everything the search returned, even what fell below threshold, if your
`search_memories` call can be made to surface that; otherwise log what you have and note the limitation).

**Inside `check_relevance()` (`llm/relevance.py`)** — one span wrapping the call, capturing the verdict and
reasoning as output. This one benefits enormously from being visible in a trace: re-read the case-6 finding
from step 6 (`docs/build/agent-manual-test-findings.md`) — that entire nondeterminism investigation was done
by manually printing debug output in a throwaway script. With this span in place, the same diagnosis is one
click in the Langfuse UI instead.

**Inside `generate_answer()` (`llm/answer.py`)** — span capturing which facts were passed in, the final
answer text, and `cited_memory_ids`.

**At the call sites of `repository.py` functions**, not inside `repository.py` itself (per the placement
rule) — e.g. in `agent/tools.py`, wrap the `save_message_with_memories` call:

```python
with langfuse.start_as_current_span(name="db.save_message_with_memories") as span:
    message_id = await save_message_with_memories(user_id, raw_message, formatted_facts)
    span.update(output={"message_id": message_id, "fact_count": len(formatted_facts)})
```

### Attaching the hashed user id and config attributes

Per ADR-007, the hashed user id belongs on the outer turn span, not scattered redundantly across every
inner span. Look up whether Langfuse's SDK has a specific concept for trace-level attributes separate from
span-level ones (often something like `update_current_trace` alongside `update_current_span`, or a
`session_id`/`user_id` parameter accepted at the trace level) — if so, that's the correct place for the
hashed id, rather than attaching it manually to each span. Write the `hash_user_id()` function from
`step-07-observability.md` Part 0 once, and call it at exactly one place: wherever the turn/trace begins.

For `settings.trace` (model, prompt version, thresholds): attach it once, at the same outer level, using
whatever the SDK's mechanism is for trace-level metadata — this is what makes a run reproducible from its
trace alone, per the design doc's requirement, and repeating it on every inner span would be redundant and
would cost quota for no benefit.

---

## Pitfalls

- `get_client()` must actually run, and `instrument_all()` must run after it and before any `Agent(...)` is
  constructed — verify this ordering by checking `tracing.py` is imported early enough in every entry point.
- Manual spans only nest correctly if created within the same async execution context as the agent run. If
  you ever run retrieval logic outside of a tool call (e.g. directly from a script, not through
  `agent.run()`), there is no outer trace for it to nest under — that's fine for isolated testing, but don't
  be surprised when such a span appears as its own top-level trace rather than nested.
- Forgetting `flush()` in short-lived scripts is the single most likely reason a script "runs fine" but
  nothing appears in Langfuse.
- Don't attach the raw `user_id` to any span — only the hashed value, and only once, at the trace level.
- Logging *only* candidates that passed the threshold defeats part of the point — `phase-6-observability.md`
  explicitly wants rejected candidates visible too, since that's what makes the threshold sweep's effects
  inspectable later.

## Done when

- `LANGFUSE_DEBUG=1` shows spans being created AND successfully exported (not just created) on a test run.
- A trace in the Langfuse UI shows: the outer agent run, nested LLM/tool call spans from Pydantic AI, and
  your manual retrieval/relevance/answer/DB spans nested correctly beneath them — not as separate traces.
- The hashed user id appears at the trace level exactly once; grepping your own span-attribute code confirms
  no raw id is ever passed anywhere.
- You can re-diagnose the step-6 Nobu nondeterminism finding by reading a trace in the UI, not by adding
  print statements to a script.
