# ADR-002 — LLM-inferred intent, clarify on doubt, stateless turns

- **Phase:** 1 — Interaction and intent model
- **Date:** 2026-09-17
- **Status:** accepted (two implementation choices deferred, see phase-1 doc)

## Context

Messages arrive as free text in a DM. The system must decide whether each one is a fact to store or a
question to answer before anything else can happen. Phase 0 gates releases on both fabrication and
false abstention, so a routing error is expensive: a question mistaken for a fact is silently
swallowed, and a fact mistaken for a question produces an answer about nothing.

## Options considered

### Option A — Explicit commands (`/remember`, `/ask`)
Routing accuracy becomes 100% by construction. Rejected: pushes the hard part onto the user, removes
the intent-classification eval surface, and makes the bot feel like a CLI.

### Option B — Pure LLM inference, always act on the model's guess
Best experience when right. Rejected on its own: a confident misroute produces a gated failure, and
nothing in the design catches it.

### Option C — LLM inference with a clarification path on low confidence
Chosen. Keeps natural-language input, bounds the cost of misrouting, and turns hard cases into
labelled data.

### Option D — Conversational context across turns
Would enable follow-up questions. Rejected for v1: session boundaries, expiry, and context-dependent
retrieval are real design work, and point-lookup scope does not need them.

## Decision

Intent is inferred by the LLM. Categories are feed, question, ambiguous, unclassifiable, command.
Ambiguous cases prompt the user rather than being guessed. Each message is handled standalone with no
carried conversational context. Unclassifiable messages get a fixed non-LLM reply. Commands in v1 are
`/start`, `/help`, and `/forget`; the last wipes all of the user's memories after a confirmation step.

Deferred: whether classification is its own LLM call or folded into the agent (to Phase 4), and the
mechanism for the clarification round trip.

## Why

Clarifying is cheap and both misroute outcomes are expensive, which makes the tradeoff one-sided. The
stateless choice is the one that costs something real — follow-up questions will not work — but it is
consistent with point-lookup scope and removes a whole category of state-management work from a
four-weekend budget.

## Consequences

Easy: routing becomes an independently measurable component; the clarification path generates
ground-truth labels for free.

Hard: the clarification round trip needs *some* way to connect the user's answer back to the original
message, which is a small violation of statelessness however it is solved. The confidence signal that
triggers clarification has to come from somewhere, and LLM self-reported confidence is not reliable by
default — this needs validating in Phase 7 rather than trusting.

Foreclosed: multi-turn refinement, pronoun references across messages.

## How this will be measured

Intent classification accuracy on a labelled eval set including deliberately ambiguous cases.
Clarification rate — too high is a usability problem, near zero suggests the confidence signal is not
working. Unclassifiable rate on real traffic.

## Revisit trigger

- Clarification fires on more than a small fraction of everyday messages.
- Family users repeatedly attempt follow-up questions, indicating statelessness is the wrong call.

## Amendment (step 6, implementation time) — clarification tool not built in v1

`request_clarification` was not implemented when the agent was wired up (`docs/design/decisions/ADR-005`,
Phase 4). The agent has only `save_memories` and `search_memories`; on ambiguous input the prompt instructs
it to prefer `search_memories` over guessing `save_memories`, since an incorrect search abstains harmlessly
while an incorrect save silently corrupts memory. This narrows the risk on one side of the ambiguity but
does not eliminate it on the other — an ambiguous message that should have been a question can still be
wrongly guessed as a feed and stored. See `docs/build/agent-manual-test-findings.md` for the full note.

This is recorded as an **open deviation**, not a superseding decision: the original reasoning in this ADR
(clarifying is cheap, both misroute outcomes are expensive) still holds, and the intent is to reconcile this
before the project is considered feature-complete against its own design docs, likely at step 9 when the
inline-keyboard mechanism this ADR anticipated for the clarification round trip is built anyway.
