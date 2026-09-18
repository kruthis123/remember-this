# Phase 4 — Agent control flow

Status: decided. Decision record: `decisions/ADR-005-control-flow.md`.

## Shape

A single agent with tools. The model's tool choice *is* the intent classification from Phase 1 — there
is no separate classifier call.

Tools:

| Tool | Purpose |
|---|---|
| `save_memories(facts[])` | persist atomic facts extracted from a feed message |
| `search_memories(query, threshold)` | vector search at strict or relaxed threshold |
| `request_clarification(reason)` | ambiguous message; ask the user which they meant |

Separate structured LLM calls, not tools, because they are internal steps the agent should not be able
to skip:

- **extraction** — raw message → list of atomic facts
- **relevance check** — weak candidates → can this question be answered from them
- **answer generation** — retrieved facts → answer with cited memory ids, or abstention

## Loop bounds

- `search_memories` at most twice per turn: strict, then relaxed. No third call.
- One `request_clarification` per turn, which ends the turn.
- Any attempt to exceed these terminates the turn with an error reply, logged as a failure.

Latency is free (ADR-001) but unbounded loops are not the same thing as slow.

## Locked decisions

**Agent, not fixed pipeline.** Chosen deliberately even though the flow is largely determined by
Phases 1–3. Be honest about what is agentic here: the model chooses the route and decides whether to
escalate to a relaxed search. It does not plan. That is a *constrained* agent, and the defensible
version of the argument is that a wider decision space would be unmeasurable at this scope, not that
constraint is a limitation.

**Structured output everywhere.** Every internal call returns a schema-validated object: intent, fact
list, relevance verdict, final answer with cited ids and an explicit abstention flag. Free-text parsing
is not used anywhere. Schema violations are logged as failures rather than retried silently.

**One reasoning model for all four steps.** Model identity is configuration, not code, so swapping is a
one-line change and a Phase 9 experiment. Embedding model is separate by necessity.

**Judge models differ from the answering model.** Same-model judging carries a self-preference bias, so
Phase 7 judges run on a different model. Which one is settled at implementation time against whatever
the university endpoints expose.

**Prompts live in code, versioned in git.** Every trace records the prompt version in force. Confirmed
or revised in Phase 9.

**No MCP.** Tools are called directly. MCP would add a process and a hop for a single consumer; the
reusability payoff does not exist yet. Reconsider if the memory store should serve other clients.

## Framework

**Pydantic AI.** Reasoning:

- Typed, schema-validated inputs and outputs are its central feature, which matches the
  structured-output decision exactly rather than bolting onto it.
- Works against any OpenAI-compatible endpoint, which is the university setup (`constraints.md` C1).
- Its instrumentation is OpenTelemetry-based, so Phase 6 stays portable across observability vendors
  instead of locking to one.
- Different enough from LangGraph to be new learning; widely enough used in 2026 to be worth naming on
  a resume ([framework comparisons](https://uvik.net/blog/python-ai-agent-frameworks/),
  [2026 roundup](https://aihaven.com/guides/best-open-source-ai-agent-frameworks/)).

Alternative considered: **OpenAI Agents SDK** — simpler, built-in tracing, but its tracing story pulls
toward the OpenAI platform, and it is a thinner learning step. Content was rephrased for compliance with
licensing restrictions.

## What must be logged for Phase 6

- tool chosen (this is the intent label), and the model's stated reason if available
- schema validation failures
- prompt version and model identity per call
- number of search passes, and where the turn terminated
- token counts and latency per step, and per turn
