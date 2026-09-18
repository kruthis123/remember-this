# ADR-010 — Prompts in git, offline-only experiments, Actions deploy, dashboard quota tracking

- **Phase:** 9 — Change workflow and lifecycle
- **Date:** 2026-09-17
- **Status:** accepted

## Context

Langfuse is in use and offers prompt management (ADR-007). Eval runs are local and manual (ADR-008). Five users,
so online experimentation has no statistical hope. University endpoints may change models without notice
(`constraints.md` C1). Everything runs on free tiers.

## Options considered

### Prompt storage
**Langfuse prompt registry** allows editing without a deploy and would exercise more of the platform. Rejected:
it introduces a state where running code and served prompt can disagree, and prompt changes stop being visible in
code review.
**Git, in code** chosen.

### Experiments
**Live traffic splitting** rejected on arithmetic — five users cannot produce a signal in any useful timeframe.
**Offline against the eval dataset** chosen.

### Model changes
**Hold the old baseline so a swap shows as a regression** would flag the change loudly but leaves the gate
permanently red for something outside your control.
**Re-establish the baseline** chosen, with a mandatory side-by-side changelog entry so the effect stays visible.

### Quota
**Dashboard tracking** chosen. **Hard kill switch** rejected as premature at this volume.

### Deployment
**GitHub Actions on push to main** rejected: it would let an unevaluated prompt change reach production silently.
**Actions on tag** chosen — tagging is a deliberate act that follows a passing eval run.
**Artifact-freshness check in the deploy job** was the alternative; more convincing to a reader, more machinery.

## Decision

Prompts in code, versioned in git, with prompt version on every trace. Experiments offline only against the
Langfuse dataset, following the queue in `phase-3-retrieval.md`. On a model change, re-baseline and record both
sets of numbers side by side. Quota and cost watched on the dashboard with no kill switch. Deploy via GitHub
Actions, triggered by a git tag rather than by a push to main.

## Why

Choosing git over the registry costs a deploy per prompt edit and buys atomicity and reviewability, which matters
more when the whole point is being able to attribute a metric change to a specific commit. The registry's
advantage — editing without deploying — is worth little at this cadence.

Re-baselining on model change is the pragmatic choice, but only survives scrutiny if the old and new numbers are
recorded together. Without that entry it is indistinguishable from hiding a regression, so the changelog entry is
part of the decision rather than a nicety.

## Consequences

Easy: every metric change is attributable to a commit; deploys are one push; no online experiment infrastructure
to build.

Hard: tag-based deploys narrow the eval-first gap to a single visible action but do not eliminate it — a tag can
still be pushed without an eval run. That residual is the weakest point in the project's discipline claim and
should be stated rather than glossed. Offline-only experiments mean conclusions rest on a ~50-case
dataset and generalise only as far as that dataset does, which should be said plainly in any writeup.

## How this will be measured

Whether the eval-before-deploy step actually happens — observable in commit history, since an eval result is
recorded with each change. Quota headroom. Number of experiments run with recorded before/after numbers.

## Revisit trigger

- A tag ships without an eval run — add the artifact-freshness check to the deploy job.
- Prompt iteration becomes frequent enough that deploy-per-edit is painful — reconsider the registry.
- User count grows enough for online experiments to be meaningful.
