# ADR-005 — Constrained tool-calling agent, structured output, single reasoning model

- **Phase:** 4 — Agent control flow
- **Date:** 2026-09-17
- **Status:** accepted

## Context

Phases 1–3 already determine the flow: classify, then either extract-and-store or search-and-answer,
with one relaxed-threshold retry. Four LLM steps exist. Agentic system design is an explicit learning
goal. Existing LangGraph experience means a different framework has more learning value here.

## Options considered

### Option A — Fixed pipeline, deterministic steps
Honest fit for a flow this determined, easiest to trace and evaluate. Rejected because it exercises none
of the agentic design skill the project is meant to demonstrate.

### Option B — Tool-calling agent with a wide decision space
Model plans freely. Rejected: nothing in point-lookup scope needs planning, and an unbounded decision
space is unmeasurable at this size.

### Option C — Constrained tool-calling agent
Chosen. Three tools, tool choice doubles as intent classification, hard bounds on search passes.
Internal steps stay outside the tool surface so the model cannot skip them.

### Framework
LangGraph excluded as already-known. **Pydantic AI** chosen for typed structured output as a first-class
concern, OpenAI-compatible endpoint support, and OpenTelemetry-based instrumentation that keeps Phase 6
vendor-portable. **OpenAI Agents SDK** was the runner-up: simpler, but thinner learning and tracing that
pulls toward one platform.

### MCP
Raised, then dropped. It is a tool-exposure protocol rather than an orchestrator, and with a single
consumer it adds a process and a network hop for no present benefit.

## Decision

One agent, three tools (`save_memories`, `search_memories`, `request_clarification`). Tool choice is the
intent classification. Extraction, relevance checking, and answer generation are separate
schema-validated calls, not tools. At most two search passes and one clarification per turn. Structured
output everywhere, with validation failures logged rather than silently retried. One reasoning model for
all reasoning steps, configured not hardcoded. Phase 7 judges use a different model. Prompts in code,
versioned in git, recorded on every trace. No MCP. Framework: Pydantic AI.

## Why

Folding classification into tool choice removes a call and a failure point; the tool chosen is still a
clean intent label for evaluation, so nothing measurable is lost. Keeping extraction and answering out of
the tool surface is the important half of the decision: those steps must always run, and a model that can
choose to skip them is a source of failures that are tedious to diagnose.

Structured output is what makes every step independently evaluable — a schema gives each stage a
checkable contract. Single reasoning model keeps the variable count low so that model comparison can be a
deliberate later experiment rather than a confound from day one. Different judge model is a correctness
requirement for the eval work, not a preference.

## Consequences

Easy: one trace per turn with clear span boundaries; every step has a schema to validate against; model
swap is configuration.

Hard: the agent is constrained enough that calling it "agentic" needs honest framing — the decision space
is routing plus one escalation. Tool-choice-as-classification means a routing error and a tool error look
the same in logs unless the tool name is explicitly recorded as the intent. Pydantic AI is new to you, so
budget time for its tracing integration before assuming Phase 6 is cheap.

## How this will be measured

Tool-choice accuracy against labelled intents. Schema validation failure rate. Search passes per turn.
Per-step latency and token counts. Turn termination reasons.

## Revisit trigger

- Framework fights the tracing requirements in Phase 6 — switch to hand-rolled over the OpenAI SDK.
- The model frequently picks the wrong tool — move classification back into its own call.
- The memory store needs to serve other clients — reopen MCP.
