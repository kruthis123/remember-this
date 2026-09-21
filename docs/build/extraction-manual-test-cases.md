# Manual extraction test cases — pre-eval-harness scratch notes

These were hand-written while testing `extract_facts` in step 3, before the real Phase 7 eval harness
(step 8) existed. Recorded here so they aren't lost. **Do not treat this as the eval dataset** — step 8
builds that properly with the full metric suite and judge model; this is just the raw material.

When step 8 starts, triage each case below into `evals/data/`: keep the ones that still expose a real
decision boundary, drop ones that were just exploratory, and give each a proper expected-facts label.

## Cases

1. Nested qualifiers, three-deep (conference/colleague/paper)
2. Self-contradicting message (Tuesday retracted, Thursday correct)
3. Multiple verbatim-sensitive tokens (currency, room code, flight number, 24h time)
4. **Fact spanning multiple sentences with an uncertainty caveat** (wedding date/location/confirmation
   needed) — see below, this one found a real prompt gap.
5. Negation with implicit shared subject (old chair vs new chair)
6. Adversarial / prompt-injection-flavored input (locker combo case)
7. Terse, high information density, no full sentences (rent/landlord/phone)
8. Pure question, nothing to store (WiFi password question)
9. Long rambling message with a buried identifier (passport number)

## Finding from case 4 — recorded as the first documented fix

**Symptom:** nondeterministic output (2 vs 3 facts across repeated calls), consistently dropping "still
need to confirm the exact date" as a fact.

**Root cause, two parts:**
- No `temperature` was set on the model, so genuine boundary-case nondeterminism was indistinguishable
  from a prompt gap.
- The prompt's atomicity rule only governed how to *split* facts already decided to be worth keeping — it
  said nothing about whether a hedge/caveat/pending-action statement counts as a fact at all. Under a
  literal reading of the atomicity test, dropping it wasn't a violation.

**Fix applied:** set `temperature` low on the model (to make repeated runs comparable), and added an
explicit rule to `prompts/extraction.py` stating that a statement of uncertainty, a caveat, or a pending
action is itself a fact worth storing, not commentary to discard.

**Why this is worth keeping as a named case:** it is a real trace → diagnosis → fix → (future) regression
guard example, which `docs/design/phase-9-change-workflow.md` explicitly calls out as a demonstration
artifact worth having in the finished project.
