# ADR-008 — Generated-and-reviewed dataset, Langfuse-native harness, no-regression gate

- **Phase:** 7 — Evaluation
- **Date:** 2026-09-17
- **Status:** accepted

## Context

Evaluation is the primary learning goal. The eval harness precedes a working bot (ADR-001). Real traffic will
be too sparse to learn from, so the dataset must be constructed. Both fabrication and false abstention are
release gates. Langfuse Cloud Hobby is the observability and eval platform (ADR-007).

## Options considered

### Dataset origin
**Hand-written** rejected: several hundred distractor memories is a wasted weekend, and the user does not want
to author cases.
**Fully generated, unreviewed** rejected: generated cases carry lexical leakage, same-model bias, and ambiguous
ground truth, all of which silently inflate scores.
**Generated then human-reviewed** chosen. Review is the quality gate, targeted at those three failure modes.

**Amendment (see `constraints.md` C7):** labelled cases are authored by Claude rather than by a provider model —
a fourth model family, and materially better at indirect phrasing and unambiguous ground truth. The provider's
`llama3.1:8b` generates only the bulk distractor corpus, where quality is irrelevant. This keeps a real
generation pipeline in the repo while putting the strongest available author on the part that determines whether
the metrics mean anything.

### Ground truth
**Reference answer only** would make end-to-end failures hard to localise.
**Expected memory ids only** would not grade answer quality.
**Both** chosen — retrieval and generation become independently measurable.

### Harness
**Langfuse-native** chosen: datasets, experiments, and run comparison come with the platform already in use.
**Own harness pushing results to Langfuse** rejected for v1: more portable and CI-friendly, but more code and no
CI is planned anyway.

### Execution
**Local only** chosen. **CI on pull requests** rejected: university LLM endpoints may not be reachable from a
hosted runner, and the automation is not worth fighting that.

### Gating
**Absolute thresholds** rejected as impractical this early — nothing is known about achievable levels.
**No-regression against a recorded baseline** chosen.

## Decision

LLM-generated dataset, reviewed by hand: a few hundred distractor memories plus 40–60 labelled cases carrying
expected facts, expected memory ids, a reference answer, and an expected-abstention flag. Nine metric suites
mixing deterministic assertions and LLM judges. Judge model differs from the system model; generator model
differs from both where possible. 50 cases hand-labelled to validate judge agreement, reported with a
chance-corrected statistic. Langfuse-native datasets and experiments, run locally on demand. No-regression gate
on faithfulness and false-abstention rate. Latest-value cases excluded from the dataset.

## Why

Generation plus review is the only option that fits both the time budget and the requirement that numbers mean
something. Naming the three specific generation failure modes turns "review the cases" from a vague instruction
into a checkable task.

Requiring both kinds of ground truth is what makes the earlier component-level decisions payable — without
expected ids, a failure could be blamed on retrieval or on the answer step with no way to tell.

Judge validation against 50 hand labels is the load-bearing part of the whole phase. It is what separates
using judges from trusting them, and it is the step most commonly skipped in projects of this shape.

## Consequences

Easy: dataset construction costs an afternoon rather than a weekend; run comparison and score storage come free
with Langfuse; every metric traces to a component.

Hard: dataset quality now depends entirely on the review step, which is manual and easy to rush. Scores consume
Hobby quota, so a full sweep has a real budget cost worth measuring before relying on frequent runs. With ~50
cases, a single flipped case moves a metric by two points, so noise and signal are hard to separate — mitigated
by reading which cases moved rather than only the aggregate. And a purely procedural gate with no CI depends on
discipline; if it slips, the eval-first claim becomes untrue.

Foreclosed for now: statistical significance testing (dataset too small), CI-enforced gating.

## How this will be measured

Judge/human agreement on the 50-case validation set. Gated metrics against baseline. Quota consumed per full
run. Number of dataset cases originating from real production failures — a direct measure of whether the
trace-to-dataset loop is actually running.

## Revisit trigger

- Judge agreement is poor after rubric revision — switch judge model or decompose the judgement into smaller
  checks.
- Metric noise makes regressions unreadable — grow the dataset.
- The procedural gate is skipped more than once — automate it with a hook.
- University endpoints become reachable from CI — move eval into pull-request checks.
