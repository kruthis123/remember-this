# Step 8 — Eval dataset and harness

Design references: ADR-008 and `phase-7-evaluation.md` (read both fully before starting — this step
implements them close to literally), the LongMemEval adapter and its docstring
(`evals/generate/adapt_longmemeval.py`), and `docs/build/agent-manual-test-findings.md` (the step-6
findings that become regression-guard cases here).

This is the largest step so far in design surface, not necessarily in code volume. Do it in the phases
below, in order — later phases depend on earlier ones being real, not stubbed.

No Telegram, no webhook. Everything runs against `remember_this.agent.runner.run_turn` and the repository
functions directly, exactly like your existing test scripts.

---

## Phase 0 — Concepts you need first

### What "the eval harness" actually has to do, end to end

For each labelled case: reset/seed a clean store for a throwaway user id, feed in the case's
`feed_messages` through `run_turn` (or directly through `save_memories`'s underlying functions — decide
this in Phase 3), ask the case's `question` through `run_turn`, then run the nine metric suites against
whatever came back, comparing against the case's ground truth (`evidence_feed_indices`,
`reference_answer`, `expect_abstention`). Record scores. Repeat for every case. Aggregate. Compare against
a baseline.

That's the whole shape. Everything below is about doing each piece correctly rather than doing something
different.

### Two categories of metric, and why they need different code paths

**Deterministic metrics** (retrieval recall, verbatim fidelity, abstention correctness, attribution,
routing) are plain Python: compare a value against ground truth, return true/false or a count. No LLM call,
no judge, no ambiguity in what "correct" means. Write these as ordinary functions.

**LLM-judged metrics** (extraction quality, faithfulness, correctness, relevance-check quality) need a
judge model call per case, with a rubric, per `phase-7-evaluation.md`'s judge section. These need their own
small `create_agent(...)`-built agents, exactly like `extract_facts`/`check_relevance`/`generate_answer` —
same pattern, new purpose. Build these in `evals/harness/judges.py`.

**Load-bearing rule from the design docs, do not skip:** every judge agent must use `judge_model`, never
`llm_model`. Your `config.py` already validates `llm_model != judge_model` at startup — that guarantee only
matters if the judge code actually asks for `judge_model`. Check this explicitly when you write each judge.

### Why Langfuse datasets specifically, and what they give you

ADR-008 chose Langfuse-native over a hand-rolled harness. Concretely, this means: the 70+ cases get
uploaded as a Langfuse **Dataset**, each run of your harness against that dataset becomes a Langfuse
**Experiment**, and each case's judge/deterministic results get attached as **Scores** on that experiment's
items. This is what gives you free run-to-run comparison in the UI later, and it's why ADR-008 flagged
scores as quota-relevant — a full run over ~70+ cases and up to nine scores each is meaningfully more
observations than a single agent turn.

Look up your installed Langfuse SDK's dataset API (introspect it directly the way you did for tracing in
step 7, rather than trusting a search result — you already know the SDK has version-specific surface).
Likely primitives: creating a dataset, creating dataset items (input/expected-output pairs), and something
like `create_experiment_item` or a scoring call tied to a dataset run. Confirm the exact method names on
your installed version before writing `evals/harness/run.py`.

---

## Phase 1 — Finish the dataset before writing any metric code

You cannot build reliable metrics against an unreviewed dataset — a metric bug and a bad ground-truth label
look identical from the outside. Do this first.

**LongMemEval was dropped.** Its `single-session-user` slice turned out to be unusable without heavy manual
editing: 64% of its feed messages are the user's half of a live back-and-forth with an assistant, so most
turns end in a question directed at the system ("do you have any advice on...") rather than reading as a
standalone fact a person would type to this bot. Even several evidence turns had the real fact glued onto a
trailing question in the same sentence. Sentence-level cleanup was judged not reliably automatable and not
worth doing by hand at this volume, so the plan reverted to full generation across all seven categories
(see the ADR-008 amendment recording this reversal). `evals/generate/adapt_longmemeval.py` and
`evals/data/longmemeval_in_scope.json` are dead code/data — do not build on them.

### 1a. Generate all seven categories — done

58 cases across the seven categories, generated one category at a time with review between each:

| # | Category | File | Count | Notes |
|---|---|---|---|---|
| 1 | clean single-fact store and recall | `01_clean_single_fact.json` | 8 | baseline, no distractors by design |
| 2 | messy multi-fact store, each fact recalled separately | `02_messy_multi_fact.json` | 8 | 3 shared rambling messages, several cases per message |
| 3 | exact identifiers and proper nouns (verbatim fidelity) | `03_exact_identifiers.json` | 8 | look-alike chars, diacritics, deliberate misspellings, near-identical numbers |
| 4 | indirect phrasing | `04_indirect_phrasing.json` | 10 | `variant`: `own_content` (5) / `common_knowledge` (5), each with topical distractors, no anchor words shared with the question |
| 5 | near-duplicate distractors on the same topic | `05_near_duplicate_distractors.json` | 8 | 3 same-topic memories per case, stored as separate feed messages |
| 6 | true absence (abstention) | `06_abstention.json` | 8 | `variant`: `empty` / `unrelated` / `near_miss_entity` / `near_miss_attribute` / `near_miss_partial` |
| 7 | borderline relevance | `07_borderline_relevance.json` | 8 | `variant` per case: intention-vs-outcome, someone else's opinion, conditional, cancelled event, etc. — all `expect_abstention: true` |

Review for the three risks `phase-7-evaluation.md` names (lexical leakage, same-model bias, ambiguous
ground truth) was done during generation, case by case, rather than as a separate pass — re-check this
assumption if any case starts behaving unexpectedly during Phase 4.

**Not yet done:** turning the two `agent-manual-test-findings.md` cases (Nobu nondeterminism, the "reveal
all memories" injection case) into permanent regression-guard cases. Do this before Phase 4 — it's the
trace → dataset loop from `phase-9-change-workflow.md` actually happening, not just described, and costs
little now that the schema and seeding pipeline exist.

### The case schema, and what it deliberately excludes

```json
{
  "case_id": "csf_01",
  "category": "clean_single_fact",
  "feed_messages": ["My student id is ABCDEF."],
  "question": "What is my student id?",
  "reference_answer": "ABCDEF",
  "expect_abstention": false
}
```

**No `expected_facts` and no fact-level or memory-id ground truth at authoring time.** Two things forced
this, both worth understanding:

- Extraction is free to split one feed message into any number of atomic facts, and this project has
  deliberately chosen not to grade *how* it splits (see below) — so ground truth authored against an
  assumed split (e.g. "rent is 1450" as one fact, "due on the 1st" as another) would be fragile and
  sometimes simply wrong once real extraction runs.
- Real memory ids don't exist until a case's feed messages are actually stored during a harness run.

**Extraction quality is deferred out of this eval pass, not deleted.** The original plan (Phase 2's
"extraction quality" judge) graded whether extraction captured every fact without distortion or
over-splitting. That's now out of scope for this pass: as long as the end-to-end answer is correct, how
many atomic facts a message became is not judged. Revisit this only if end-to-end failures start tracing
back to extraction splitting badly — don't add the judge preemptively.

### 1b. The distractor corpus — built and embedded

Done: 407 unrelated notes across 20 everyday topics, generated with `generator_model`
(`evals/generate/generate_distractors.py`), filtered to exclude anything that would accidentally answer a
labelled case (a `BLOCKED_TERMS` list covering every name/subject the 58 cases reference) and anything
phrased as a question or an instruction to the bot. Embedded once, up front
(`evals/generate/embed_distractors.py`), and cached with their vectors in
`evals/data/generated/distractors_embedded.json` — this is what lets every case's seeding pass draw a
random slice without a redundant round trip to the embedding endpoint. Regenerate this cache only if the
distractor text itself changes.

Each case is seeded against a **random 100-note slice** of this cached pool, not the full 407 and not a
dedicated per-case set. A shared pool is what "realistic density" actually calls for — a family member's
memory store isn't partitioned by topic — and sampling 100 per case bounds the per-case seeding cost while
still giving retrieval real distractor volume to search through.

### 1c. Seeding is single-pass — no memory-id ground truth is collected

**Decision, superseding the original plan:** cases carry no `expected_memory_ids` and no fact-level ground
truth at all, even after seeding. `evals/harness/seed_case.py` exists and does exactly one thing: pick a
throwaway user id, insert a random 100-note slice from the embedded distractor cache directly (no LLM call
— skip extraction for distractors entirely, they're already atomic), then run the case's own
`feed_messages` through the real storage path (`save_memories`, so extraction runs for real). It prints
which real memory ids extraction produced — **diagnostic only**, for eyeballing how a message split, not
something to copy into a case file.

Why: retrieval-recall-against-a-specific-id turned out to be fragile ground truth to maintain (extraction
can legitimately split a message differently across runs or after a prompt change, and Postgres ids aren't
stable across reseeds), and it duplicates what the end-to-end answer already tells you. If the final
answer's `reference_answer` match and `cited_memory_ids` are both correct, retrieval necessarily worked —
there's no case where the answer is right but retrieval "secretly" failed. Grading only the end-to-end
outcome is enough for now. Revisit — and only then decide how to compare deterministically — if a failure
investigation genuinely needs to isolate "retrieval found the wrong things" from "the answer step
misused what it was given," and the answer/citation-level metrics alone can't tell you which.

Consequence: the **retrieval recall/hit rate** metric originally planned in Phase 3 is also dropped for
now, for the same reason.

### 1d. One unified dataset file/schema

Seven category files exist in `evals/data/generated/` (`01_clean_single_fact.json` through
`07_borderline_relevance.json`, 58 cases total), plus `distractors_embedded.json`. Each case has, at
minimum: `case_id`, `category`, `feed_messages`, `question`, `reference_answer`, `expect_abstention`. Some
categories add a `variant` field for sub-grouping (indirect phrasing, abstention, borderline relevance) —
keep reading scores broken down by `variant` where present, per those categories' own reasoning.

---

## Phase 2 — Judges

`evals/harness/judges.py`. Each judge is a small `Agent` built via `create_agent`, using `judge_model`,
with its own written rubric — same pattern as `extraction.py`/`relevance.py`/`answer.py`, new prompts.

Per `phase-7-evaluation.md`: small discrete scale, not continuous 1–10 (false precision, inconsistency).
Judges receive only the retrieved facts, the question, the answer, and the reference — nothing else, so
they can't be swayed by details irrelevant to the specific judgment.

Judges needed, per the metric suite table:

- **extraction quality** — deferred, not built this pass (see Phase 1's note). Skip this judge for now;
  revisit only if end-to-end failures trace back to how a message was split.
- **faithfulness** — given the retrieved facts and the answer, does the answer assert anything not present
  in the facts?
- **correctness** — given the reference answer and the actual answer, do they match, allowing paraphrase?
- **relevance-check quality** — this one is different: it's not judging your system's output, it's judging
  whether `check_relevance`'s own verdict was correct on borderline cases. This can likely be a
  **deterministic** comparison against a human label on the borderline-relevance cases from Phase 1,
  rather than a separate judge — re-read the metric suite table's "Method" column for this row before
  building a redundant LLM judge for something you can label directly.

### Judge validation — do this before trusting any judge score

Hand-label 30 system answers yourself (reduced from the originally planned 50, since the whole dataset is
only 61 cases), run each judge against the same frozen answers, and report raw agreement plus Cohen's
kappa. The full procedure — which 30 cases, the label definitions, blind labelling, and adding
hand-corrupted answers if real failures are too rare — is in `docs/build/step-08-hand-labelling.md`.

Built: `evals/harness/judges.py` (faithfulness: `faithful`/`unfaithful`; correctness:
`correct`/`partial`/`incorrect`), with rubrics in `evals/harness/judge_prompts.py`. Both judges use
`judge_model` at temperature 0. The faithfulness judge sees only the question, the facts stored from the
case's own messages, and the answer — never the reference answer, so support and correctness stay
separate judgments. Relevance-check quality is deterministic, not a judge.

This is explicitly called out as the load-bearing step of the whole phase. A judge you haven't validated is
a number generator with no known relationship to truth. Do not skip this to save time — if agreement is
poor, revise the rubric and re-run, don't adjust your own labels to match the judge.

---

## Phase 3 — Deterministic metrics

`evals/harness/metrics.py`. Plain functions, no LLM calls:

- **retrieval recall/hit rate against a specific id** — dropped, see Phase 1c. Not built this pass.
- **verbatim fidelity** — for cases carrying an identifier, does the answer text contain it character-for-
  character?
- **abstention correctness** — does `expect_abstention` match whether the system actually abstained?
- **attribution** — is every id in `cited_memory_ids` actually one of the ids `retrieve()` returned for that
  turn (not invented)? This is checkable without any pre-assigned ground truth — it only needs the ids the
  system itself retrieved during this run, compared against the ids it then cited.
- **routing** — did the top-level agent call the tool matching the case's intended category (`save_memories`
  for feed-only setup calls, `search_memories` for the actual question)?

---

## Phase 4 — The runner

`evals/harness/run.py`. Ties Phases 1–3 together:

1. For each case: create a fresh throwaway user id, seed a random 100-note slice of the embedded distractor
   cache directly (no LLM call), then run the case's feed messages through the real storage path
   (`run_turn`, so extraction runs for real) — reuse `evals.harness.seed_case.seed_case` rather than
   duplicating this logic.
2. Ask the question through `run_turn`.
3. Run every applicable metric/judge against the result.
4. Push the case's scores to the Langfuse dataset run (per Phase 0's Langfuse-dataset note).
5. Clean up the throwaway user's data.
6. Aggregate: report each metric suite's score, **read as the pairs `phase-7-evaluation.md` specifies**
   (faithfulness with false-abstention rate) — never as isolated numbers. The retrieval-recall/abstention
   pairing from the original plan no longer applies since retrieval recall isn't graded this pass.

### The baseline and gating

First full run establishes the baseline (ADR-008: no-regression, not absolute thresholds). Record it
somewhere durable — a committed file, or a named Langfuse experiment you can always diff future runs
against. Gated metrics: faithfulness, false-abstention rate. Everything else reported, not gated.

With ~70-plus cases (larger than the originally planned ~50 thanks to Phase 1), a single flipped case moves
a metric by roughly 1.5 points rather than 2 — still small enough that reading which specific cases moved
matters more than trusting the aggregate alone, per `phase-7-evaluation.md`.

---

## Phase 5 — Threshold sweep

Not a separate step — this is `phase-3-retrieval.md`'s mandatory first experiment, and this harness is what
makes it possible. Once Phase 4 runs end to end, re-run it across a range of `strict_threshold`/
`relaxed_threshold` values (temporarily overriding config, not editing `.env` each time) and plot/tabulate
retrieval recall against fabrication and false-abstention rates. This is the artifact `phase-3-retrieval.md`
calls "one of the more demonstrable artifacts this project can produce" — don't treat it as optional
polish.

---

## Pitfalls

- Building metric code against an unreviewed dataset means you can't tell a metric bug from a bad label —
  finish Phase 1 first.
- Judges must use `judge_model`, never `llm_model` — check every judge agent construction explicitly.
- Don't build a separate LLM judge for something a deterministic comparison already covers (the
  relevance-check quality row is the likely trap here).
- Skipping judge validation to save time defeats the point of the entire phase — it's explicitly called out
  as the most commonly-skipped, most load-bearing step.
- Quota: a full run's worth of scores is real Langfuse Hobby-tier consumption — measure the cost of one run
  before assuming you can run this as often as you'd like.

## Done when

- All seven categories exist as generated, reviewed cases (~56 total), including both step-6 findings
  turned into regression guards for the borderline-relevance and injection categories.
- Judge validation against 50 hand labels is reported with raw agreement and Cohen's kappa, for every judge
  in use.
- A full harness run produces per-case and aggregated scores, visible as a Langfuse experiment.
- A recorded baseline exists, and you can state what "no regression" means operationally for this project.
- A threshold sweep has been run at least once, with results you can point to.
- You can state, in one sentence, why extraction-quality grading and retrieval-recall-against-a-specific-id
  were both deferred, and what evidence would bring either back into scope.
