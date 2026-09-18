# ADR-004 — Pure semantic retrieval, verbatim query, threshold-gated, retry on miss

- **Phase:** 3 — Retrieval architecture
- **Date:** 2026-09-17
- **Status:** accepted

## Context

Point lookup over hundreds of atomic facts per user, no metadata to filter on (ADR-003). Both
fabrication and false abstention are release gates, and latency is free (ADR-001). Learning vector
retrieval is an explicit study goal, independent of whether hundreds of rows require an index.

## Options considered

### Option A — Brute-force scan, all memories into the prompt
Legitimate at this corpus size and would work. Rejected because it teaches nothing about retrieval and
sidesteps the study goal. Worth keeping as a comparison baseline in an experiment, since "the simple
thing was nearly as good" is a finding worth having.

### Option B — Pure semantic vector search
Chosen for v1. Single mechanism, clean baseline for later experiments.

### Option C — Hybrid semantic + lexical from the start
Likely better on exact identifiers like `ABCDEF`, where lexical matching is strong. Rejected for v1
only because it removes the baseline that would demonstrate its value.

### Option D — Fixed top-k
Rejected: always returns candidates, so the system can never honestly abstain.

### Option E — Threshold gate
Chosen. Enables abstention, at the cost of one hard-to-set number.

### Option F — Single pass, abstain on miss
Rejected: false abstention is a gated failure and there is no cost pressure against retrying.

## Decision

Embed the question verbatim. Vector search over the calling user's memories only. Accept candidates
above a **strict** similarity threshold, with a generous hard cap as a safety valve. On zero candidates,
exactly one retry at a **relaxed** threshold, with an LLM relevance check deciding whether the weaker
candidates can actually answer the question; abstain if it says no. No rewriting, no reranking, no
lexical leg in v1 — each becomes a measured experiment later.

## Why

Every deferral here is a deferral *into an experiment with a number attached*, which is the point of the
project. Building hybrid retrieval and reranking up front would produce a better bot and a worse
portfolio, because there would be no baseline to show improvement against.

The threshold choice is the substantive one. It is what converts "the model was unsure" into a product
behaviour, and it couples the two gated metrics — so it forces the tradeoff to be confronted with data
rather than hidden behind a top-k that always answers.

## Consequences

Easy: one moving part, so the threshold sweep is interpretable. Abstention becomes a designed behaviour
rather than an emergent one.

The two-tier gate — cheap numeric filter for clear cases, LLM adjudication for borderline ones — falls
out of having both failure modes gated and latency free. The relevance check is the last line of defence
against fabrication on weak retrieval, so it is a primary eval target rather than plumbing.

Hard: two thresholds to calibrate instead of one. Exact-identifier recall may be weak without a lexical leg, and identifiers are precisely where
Phase 0 demands verbatim fidelity — expect this to show up in the eval. Cosine similarity is not
calibrated confidence, so threshold tuning will be noisier than it looks. Retry needs something to
vary, which pushes against the verbatim-query rule.

Foreclosed for v1: filtered retrieval, date narrowing, multi-hop.

## How this will be measured

Retrieval recall against labelled memory ids. Hit rate above threshold. Both read together with
fabrication and false-abstention rates, since the thresholds move all four. The sweep curve over strict
and relaxed thresholds is itself a deliverable. The relevance check gets its own precision/recall on
borderline cases.

## Revisit trigger

- Identifier-style questions fail retrieval — add the lexical leg.
- No threshold setting satisfies both gates simultaneously — retrieval is the bottleneck; try rewriting,
  reranking, or metadata.
- Brute-force baseline matches vector search on the eval set — say so honestly in the writeup.
