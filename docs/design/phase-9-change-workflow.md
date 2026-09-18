# Phase 9 — Change workflow and lifecycle

Status: decided. Decision record: `decisions/ADR-010-change-workflow.md`.

## Prompt management

**Prompts live in code, versioned in git.** Not in Langfuse's prompt registry, despite Langfuse being the
platform. Reasons: a prompt change is reviewable in a diff alongside the code that depends on it, and a deploy
is atomic — there is no state where the running code expects one prompt and the registry serves another.

Cost accepted: editing a prompt requires a deploy. At this cadence that is not a real constraint.

Every trace records the prompt version in force (ADR-005), so a trace can always be tied back to a commit.

## Experiments

**Offline only, against the eval dataset.** No live traffic splitting — with five users, any online experiment
would take months to produce a signal and the signal would be noise. Stated as a scale conclusion rather than a
capability gap.

Experiment queue is already defined in `phase-3-retrieval.md`: threshold sweep first (mandatory), then query
rewriting, reranking, hybrid retrieval, metadata. Each one is a run against the same dataset with a recorded
before/after.

## Model changes

University endpoints may change models underneath the project. When that happens the **baseline is
re-established** against the new model.

The hazard in that choice: silently re-baselining absorbs a regression and makes it invisible. Mitigation —
record both numbers side by side in a changelog entry, so the model swap and its effect on every metric are
visible even though the reference point moves. A re-baseline without that entry is indistinguishable from
hiding a regression.

## Quota and cost

Tracked on the dashboard, no kill switch:

- LLM and embedding calls against the university quota
- Langfuse units against the Hobby allowance, which eval runs consume through scores (ADR-008)
- Cloud Run requests and Neon compute hours, both expected to stay far inside free tiers

Expected monthly cost is zero. A non-zero bill means something is misconfigured.

## Deployment

**GitHub Actions on tag**, deploying the container to Cloud Run. Feasible because deployment does not need the
university LLM endpoint, unlike eval runs.

Pushing to main does not deploy. Tagging does, and tagging is the deliberate act that follows a passing eval run.
That is what closes the gap between an automated deploy and a manual eval gate: reaching production requires a
step you cannot take absent-mindedly.

Not perfect — a tag can still be pushed without running evals — but the discipline is now attached to a single
visible action rather than to every commit.

## Change workflow, end to end

1. Change a prompt, threshold, or model in code.
2. Run the eval suite locally against the Langfuse dataset.
3. Compare to baseline. Gated metrics must not regress (ADR-008).
4. Inspect which individual cases moved — at ~50 cases, aggregates alone are unreliable.
5. Commit, with the eval result recorded, and push to main. Nothing deploys.
6. Tag the commit. The tag triggers the deploy.
7. Watch traces and thumbs-down for a few days; feed new failures back into the dataset.

## Artifacts the repo should end up containing

Deferred in detail to Phase 10, but the change workflow should be producing them as a by-product rather than as
a separate writing effort:

- the ADR trail in `decisions/`
- the threshold sweep curve
- judge validation agreement numbers
- at least one documented failure: trace, diagnosis, fix, and the eval case that now guards it
- a baseline-versus-current metrics table
- cold and warm latency and token cost per turn
