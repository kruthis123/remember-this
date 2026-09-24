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

**Second amendment (step 7/8 boundary, implementation time): adopt an external benchmark subset for the
in-scope point-lookup and abstention categories, generate only what it does not cover.** LongMemEval
(Wu et al., ICLR 2025, arXiv:2410.10813) was found to contain a `single-session-user` question type that is
structurally identical to this project's point-lookup contract: a fact stated in passing inside a longer,
multi-topic message, recalled precisely by a later question, with real topical distractors already present
from the surrounding conversation. Its abstention instances of the same type test discrimination against a
genuinely adjacent distractor (e.g. asked about a hamster, only a cat was ever mentioned), which is harder to
author convincingly by hand than it looks.

70 of LongMemEval's 500 instances are in scope (64 `single-session-user` point-lookup + 6 same-type
abstention); the remaining 430 are excluded because they require capabilities this project explicitly
scopes out — `knowledge-update` (latest-value, ADR-003 non-goal), `multi-session` (aggregate/multi-hop,
ADR-001 non-goal), `temporal-reasoning` (ADR-003 non-goal), `single-session-assistant` (fact originates in
an assistant turn, nothing for this system to have stored), and `single-session-preference` (evaluates
response-style personalization, not fact recall). See `evals/generate/adapt_longmemeval.py`'s docstring for
the full per-category reasoning and the adaptation procedure (only user turns kept; `has_answer`-flagged
turns become the retrieval ground truth).

This does not replace generation — it replaces the *self-authored labelled-case* half of the original plan
for the categories it covers. The distractor corpus and all case categories LongMemEval does not address
(verbatim-identifier fidelity, multi-fact splitting per one message, prompt injection, the category-vs-
occasion inference boundary from `relevance.py` rule 2a) are still generated per the original plan below.
The externally-authored cases also remove the self-authorship-bias caveat noted above, for the categories
they cover.

Every adapted case ships with `reviewed: false` and must be read by hand before being trusted — the adapter
discards assistant turns, which may occasionally remove context a question leans on, and LongMemEval's
answers are reference strings meant for its own LLM judge, not verified exact-match targets.

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

Dataset combines an externally-authored subset with generated cases. 70 point-lookup/abstention cases adapted
from LongMemEval's `single-session-user` slice (see amendment above), plus generated cases — reviewed by hand
— for everything LongMemEval doesn't cover: verbatim-identifier fidelity, multi-fact splitting, prompt
injection, and the category-vs-occasion relevance boundary. A distractor corpus of unrelated memories,
generated wholesale, still fills out realistic store density. Nine metric suites mixing deterministic
assertions and LLM judges. Judge model differs from the system model; generator model differs from both where
possible. 50 cases hand-labelled to validate judge agreement, reported with a chance-corrected statistic.
Langfuse-native datasets and experiments, run locally on demand. No-regression gate on faithfulness and
false-abstention rate. Latest-value cases excluded from the dataset.

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
with Langfuse; every metric traces to a component. The LongMemEval subset is externally authored, so it
strengthens rather than merely maintains the self-authorship-bias mitigation, for the categories it covers.

Hard (new, from the LongMemEval adoption): licence status for the dataset was not confirmed at adoption time —
treated as research-use-only pending verification, cited in any public writeup. The adapter's user-turns-only
simplification needs spot-checking, not just assuming, before the 70 cases are trusted. And LongMemEval covers
only two of the seven case categories `phase-7-evaluation.md` lists as deliberate coverage — the harder-to-
author categories (verbatim fidelity, multi-fact splitting, injection, inference-boundary cases) are still
entirely on generation-plus-review, so that discipline still matters exactly as much as originally planned.

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
- LongMemEval's licence turns out to restrict this use — fall back to fully self-authored point-lookup/
  abstention cases for those two categories.
- Spot-checking the adapted cases reveals the user-turns-only simplification breaks too many of them —
  either re-include relevant assistant turns as inert context or drop the affected cases.
