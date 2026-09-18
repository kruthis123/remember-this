# Phase 3 — Retrieval architecture

Status: decided, one open item. Decision record: `decisions/ADR-004-retrieval.md`.

## Pipeline

```
question
  → embed verbatim (no rewriting)
  → vector search, strict similarity threshold
  → on miss: one retry at a relaxed threshold, then an LLM relevance check on the weak candidates
  → if the relevance check rejects them: "I have nothing recorded about that"
  → else: answer from the retrieved fact(s), citing memory + date
```

## Locked decisions

**Pure semantic, no lexical leg.** Vector search only, which is the study goal. Also gives a clean
baseline that a hybrid experiment can later be measured against — adding hybrid first would leave
nothing to compare it to.

**Question embedded verbatim.** No rewriting, expansion, or decomposition in v1. Rewriting becomes a
Phase 9 experiment with a before/after eval number attached, which is more valuable than having it in
the baseline.

**Similarity threshold, not fixed top-k.** Top-k always returns something, which makes honest
abstention impossible — the least-bad match gets presented as an answer. A threshold is what allows
"nothing relevant". Practical note: threshold-only is unbounded on the other side, so a hard cap on
results is still needed as a safety valve, sized generously enough that it never becomes the effective
selector.

**One retry, at a relaxed threshold, adjudicated by an LLM relevance check.** See retry semantics
below. Justified by the Phase 0 rule that false "I don't know" is a gated failure and latency is free.

**No reranking in v1.** Deferred as a later experiment, same reasoning as query rewriting.

## The thresholds are a calibration problem, not constants

Every gated metric moves with these numbers. Too high, false abstentions. Too low, fabrications from
irrelevant context. They cannot be guessed — they have to be swept against the eval set and chosen from
the curve, and that sweep is one of the more demonstrable artifacts this project can produce.

Note also that raw cosine similarity is not calibrated confidence. Two unrelated short sentences can
score deceptively high. Watch for that when interpreting the sweep.

## Retry semantics

Exactly one extra pass. On a first-pass miss:

1. Re-search with a **lowered threshold** (the relaxed threshold).
2. Pass the weaker candidates to an **LLM relevance check**: does any of this actually answer the
   question? Not "is it topically similar" but "can the question be answered from this".
3. If the check says yes, answer from it. If no, abstain.

No third pass. The query is never rewritten, so the verbatim rule holds throughout.

Two consequences worth noting. There are now **two** thresholds to calibrate, strict and relaxed, and
the gap between them defines the zone where the LLM adjudicates rather than the score. And the relevance
check is a guardrail in its own right: it is the thing standing between weak retrieval and a
fabrication, so it is a first-class eval target, not plumbing.

The pipeline shape becomes: cheap numeric gate for the easy cases, expensive semantic gate for the
borderline ones. That is a reasonable design to be able to defend, and it exists specifically because
both gated failures are unacceptable and latency is free.

## Deferred experiments, in likely order of payoff

1. Strict/relaxed threshold sweep (not optional — it is the calibration above)
2. Query rewriting on the first pass
3. Reranking retrieved candidates
4. Hybrid semantic + lexical
5. Metadata-filtered retrieval, which requires reopening ADR-003

## Eval implications

- Retrieval is evaluated as its own component: labelled memory ids per question, recall@k and hit rate
  above threshold.
- Because abstention depends on the threshold, retrieval metrics and abstention metrics have to be read
  together. Neither is interpretable alone.
- Latest-value cases stay out of the eval set (see `phase-2-memory-representation.md`).

## What must be logged for Phase 6

- the query embedded, and which model produced the embedding
- candidate memory ids with similarity scores, including those rejected by the threshold
- strict and relaxed threshold values in force for that run
- whether a retry happened, and the relevance check's verdict and reasoning
- final decision: answered or abstained
