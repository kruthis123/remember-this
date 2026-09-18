# ADR-003 — Raw message plus atomic extracted facts, append-only, no metadata

- **Phase:** 2 — Memory representation
- **Date:** 2026-09-17
- **Status:** accepted

## Context

Point-lookup recall over hundreds of memories, with multi-fact messy input in scope and a confirmation
reply required on every store. Latest-value lookup is a declared non-goal but a likely v2 feature, so
the representation must not foreclose it.

## Options considered

### Option A — Store raw messages only, interpret at read time
Simplest write path, no extraction eval surface, and retrieval units are large and multi-topic, which
hurts precision. Rejected.

### Option B — Store extracted facts only
Compact and focused, but the original wording is gone, so extraction errors become undetectable after
the fact and there is nothing to judge extraction against. Rejected.

### Option C — Store both; one memory per atomic fact
Chosen. Raw text preserved as ground truth, facts as retrieval units.

### Option D — Option C plus LLM-extracted metadata (entities, tags, confidence)
Enables filtered and hybrid retrieval. Deferred: each field is another extraction failure mode to
evaluate, and none of it pays off until retrieval is shown to need it.

### On contradictions
Considered detect-and-warn and detect-and-ask. Both require comparing a new fact against existing
memories on every write, which is the supersession problem in disguise — the thing explicitly deferred.
Chosen instead: store side by side, accept stale recall, exclude those cases from the eval set.

## Decision

Two record types: verbatim Message, and Memory holding one atomic extracted fact linked to its source
message. Structural fields only (ids, user id, timestamps) — no LLM-derived metadata. Extraction runs
synchronously before the confirmation reply. Store is append-only; `/forget` deletes everything for a
user. Contradicting facts coexist unresolved.

## Why

Splitting into atomic facts is what makes the multi-fact contract case work, and it makes each
retrieval unit single-topic. Keeping the raw text costs almost nothing at this scale and is what makes
extraction evaluable at all — without it, the write-path eval layer from ADR-001 does not exist.
Append-only is a smaller decision than it looks: nothing in v1 mutates, and the audit trail is useful
for debugging. Withholding metadata is a deliberate bet that plain semantic retrieval suffices at
hundreds of rows; the retrieval metrics will settle it rather than intuition.

## Consequences

Easy: extraction quality becomes measurable; per-fact retrieval; a clean upgrade path to supersession
because `created_at` and raw text are both retained.

Hard: stale answers are possible and contradict the Phase 0 gate on confident wrongness. Handled by
excluding latest-value cases from the eval set, which must be stated in Phase 7 rather than left
implicit. Retrieval in Phase 3 has no metadata to filter on, so it is purely semantic.

Foreclosed for v1: correcting a single fact, any filtered or hybrid retrieval.

## How this will be measured

Extraction correctness and completeness against raw text, rubric-judged. Facts extracted per message,
watched for over- and under-splitting. Retrieval recall — if it is the weakest metric, metadata is the
first thing to add.

## Revisit trigger

- Retrieval recall is the limiting metric — add metadata and filtering.
- Family users start correcting facts often — selective update or delete is needed, and append-only
  needs a supersession model.
- Over-splitting appears: facts that only make sense together get separated and become unretrievable.
