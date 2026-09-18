# ADR-001 — v1 scope, correctness definition, and failure preference

- **Phase:** 0 — Scope, product contract, and success definition
- **Date:** 2026-09-17
- **Status:** accepted

## Context

The project exists to build LLM observability and evaluation skill; the bot is the vehicle. Four
weekends, a handful of family users, university-provided LLM and embedding APIs. Scope must stay
small without collapsing the eval surface to something trivial.

## Options considered

### Option A — Point lookup over clean single-fact messages
Smallest possible build. Rejected: with clean inputs and a tiny store, every metric pins at 100%.
No headroom means no experiments worth running, which defeats the purpose.

### Option B — Point lookup, but messy multi-fact inputs and a populated store
Same feature set as A. Difficulty comes from input distribution and distractor density rather than
from query taxonomy. LLM extraction on the write path adds a whole eval layer at low build cost.

### Option C — Add latest-value and aggregate query types to v1
Richer eval surface, but pulls in memory supersession and multi-memory reasoning — two hard design
problems that would consume the whole time budget before any eval work happened.

### Option D — Deterministic-only evaluation
Rejected as a framing error: deterministic assertions and LLM judges are layers of one stack, not
alternatives. Cheap assertions form a floor; judges handle the semantic part.

## Decision

Option B. Point lookup only, with three deliberate widenings of the input distribution:
multi-fact rambling messages, abstention cases where nothing was stored, and paraphrase-varied
queries. Yes/no questions, latest-value lookup, aggregates, and proactive messaging are non-goals.

Correctness requires grounding, verbatim fidelity for identifiers, responsiveness, and honesty about
absence, plus attribution of the source memory and its date. Both fabrication and false abstention are
release-gating failures; latency is the only freely tradeable dimension.

Eval harness precedes a working bot.

## Why

Feature scope and eval richness turned out to be nearly independent. Difficulty lives in the data,
not the feature list, so the cheap path to a real eval surface was widening inputs rather than adding
capabilities. Extraction-on-write was the highest-value single addition: it creates a rubric-judged
eval layer and simultaneously powers the store confirmation the user wanted.

Ranking confident-wrongness as the worst failure follows from the users being family who will trust the
answers. Refusing to treat abstention as a safe fallback is the sharper half of that decision: it
forbids the easy design where the system hedges under uncertainty, and forces retrieval quality to
carry real weight. Zero LLM cost pressure and unlimited latency budget make multi-call verification
affordable, so there is no excuse for either failure.

## Consequences

Easy: a small, finishable build; a defensible story about measuring before optimising; six eval
metrics plus judge validation from a two-feature bot.

Hard: with neither correctness failure tolerated, retrieval has to be genuinely good rather than
merely cautious. The metric set must be reported as a pair, never as a single score, since fabrication
and false abstention are each trivially minimised at the other's expense. The eval dataset now has to be constructed by
hand rather than harvested, since five family members will not generate meaningful traffic volume.

Foreclosed for v1: anything requiring reasoning across multiple memories. Memory representation
(Phase 2) must still avoid designs that make latest-value lookup impossible to add later.

## How this will be measured

Release gate: fabrication rate on the eval set, judged for faithfulness. Reported alongside
abstention rate so that improvements in one at the cost of the other are visible. Latency and token
cost recorded per trace, reported but not gated.

## Revisit trigger

- Eval scores plateau above ~95% with no meaningful failures left to study — scope was too easy,
  promote latest-value lookup into scope.
- Real family usage shows most questions are out of scope — the point-lookup restriction is wrong
  about actual usage and the contract needs rewriting.
