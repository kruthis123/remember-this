# Step 8 — Hand labelling for judge validation

Companion to `step-08-eval-harness.md` Phase 2. The goal: find out whether the two judges in
`evals/harness/judges.py` agree with you. Until this is done, a judge score is a number with no known
relationship to reality.

---

## What you are labelling

You label **the system's actual answers**, not the dataset cases. For each selected case you need one record:

| Field | Where it comes from |
|---|---|
| `case_id` | the case file |
| `question` | the case file |
| `expect_abstention` | the case file |
| `reference_answer` | the case file |
| `stored_facts` | the `fact_text` of every memory stored from the case's own `feed_messages` (not distractors) |
| `answer` | what `run_turn` returned for the case's question |

The judges and you must look at **exactly the same records**. Generate the answers once, freeze them in a
file, then label from that file. Never re-run the system between labelling and judging, or you'll be
comparing verdicts on different answers.

`stored_facts` is what the faithfulness judge treats as "everything the assistant legitimately knew".
Distractors are excluded because they're chosen to be unrelated to every question.

---

## Which 30 cases

Four per category, weighted toward the harder cases so both good and bad answers show up, plus the two
regression guards:

| Category | Cases |
|---|---|
| clean single-fact | csf_01, csf_05, csf_07, csf_08 |
| messy multi-fact | msf_02, msf_05, msf_06, msf_08 |
| exact identifiers | eid_01, eid_04, eid_05, eid_07 |
| indirect phrasing | ip_01, ip_05 (own content), ip_06, ip_09 (common knowledge) |
| near-duplicate distractors | nd_02, nd_04, nd_07, nd_08 |
| abstention | ab_02, ab_05, ab_06, ab_08 |
| borderline relevance | br_02, br_04, br_08, br_09 |
| regression guards | br_10, inj_01 |

### If the system gets almost everything right

Agreement statistics need both good and bad examples. If nearly every answer is correct and faithful, kappa
becomes unstable or meaningless, even when you and the judge agree on every record.

If the real run produces fewer than about 6 failing records per judge, add **hand-corrupted answers**:
copy a real record and edit the answer to be wrong in a realistic way. Examples: change one character of
an identifier, swap in a near-duplicate's value (nd_07's `4471` instead of `4417`), answer an abstention
case with a plausible guess, or add an invented detail. Mark these records `corrupted: true` so they can be
reported separately. This is standard practice for judge validation, not cheating. You're testing whether
the judge can tell good answers from bad ones, and that needs bad ones to test on.

---

## How to label

Label **blind**: fill in every label before you look at a single judge verdict. Seeing the judge's answer
first anchors you towards it and inflates agreement.

For each record, give two labels using the same definitions the judges use. The definitions below are
condensed from `evals/harness/judge_prompts.py`; if they ever disagree, the prompt file is the source of
truth.

### Faithfulness: `faithful` or `unfaithful`

Look only at `stored_facts` and `answer`. Ignore `reference_answer` entirely; faithfulness is about support,
not correctness.

- **unfaithful** if the answer states anything not in `stored_facts` and not following directly from them:
  an invented value, a detail filled in from what's typical, a claim about what the user did that isn't
  stated, or an identifier with any character changed.
- One allowed exception: a universally true property of an entity named in a fact ("Nobu is a Japanese
  restaurant"). An occasion-specific detail ("you ate sushi at Nobu") is not allowed.
- Rephrasing, leaving things out, and saying "I don't have that recorded" are all **faithful**.
- If `stored_facts` is empty, any specific claim about the user is **unfaithful**.

### Correctness: `correct`, `partial`, or `incorrect`

Compare `answer` against `reference_answer`, using `expect_abstention`.

When the system should answer (`expect_abstention: false`):
- **correct**: conveys the reference's key content; identifiers match exactly.
- **partial**: some of the key content, but missing part of it or mixed with something wrong.
- **incorrect**: wrong, missing, or says nothing is recorded.

When the system should abstain (`expect_abstention: true`):
- **correct**: clearly says the information isn't recorded (mentioning related info it does have is fine).
- **partial**: says it's unsure but still offers a guess.
- **incorrect**: gives a definite answer.

### Hard calls

When a record is genuinely ambiguous, pick the label you'd defend and write one line in a `notes` field
explaining why. Don't skip it, and don't come back and change it after seeing the judge. Ambiguous records
are exactly where rubric wording needs fixing, and your notes are how you'll find them.

---

## After labelling: measuring agreement

For each judge separately:

1. **Raw agreement**: the fraction of records where your label equals the judge's label.
2. **Cohen's kappa**: agreement corrected for chance. With `p_o` as the raw agreement and `p_e` as the
   agreement you'd expect by chance (for each label, the share of records you gave it times the share the
   judge gave it, summed over labels):

   `kappa = (p_o - p_e) / (1 - p_e)`

   `sklearn.metrics.cohen_kappa_score(human_labels, judge_labels)` computes this directly.

Rough reading: above 0.8 is strong, 0.6–0.8 is good enough to use, below 0.6 means the rubric needs work.
These bands are conventions, not laws. With 30 records the estimate is noisy, so look at the individual
disagreements rather than treating one kappa value as definitive.

Report corrupted and real records separately as well as combined. A judge that only agrees with you on
obvious corruptions isn't validated for the subtle failures real runs produce.

### When agreement is poor

Read every disagreement. For each one, decide whether:

- **the rubric was unclear**: fix the wording in `judge_prompts.py` and re-run the judge on the same frozen
  records;
- **the judge misapplied a clear rubric**: add a worked example of that exact pattern to the prompt, then
  re-run;
- **you mislabelled**: this can happen, but only change your label if you can point to the rubric sentence
  you misread. Never change a label just to match the judge.

Keep a short log of each disagreement and what you changed. It's direct evidence that the judges were
validated rather than trusted.

---

## Done when

- 30 frozen records exist (plus any corrupted records), each with your two labels and notes where needed.
- Raw agreement and Cohen's kappa are reported for both judges: real, corrupted, and combined.
- Every disagreement has been read and either explained or fixed.
