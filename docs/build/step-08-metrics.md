# Step 8, Phase 3 — `evals/harness/metrics.py`

Four plain Python functions, no LLM calls. Each one takes a case plus the real output of running that
case through the system, and returns `True`/`False` (or `None` when the metric doesn't apply to that
case). Nothing here is a judge — if a question needs model judgment, it belongs in `judges.py`, not here.

Reference these existing pieces while building:

- `evals/data/generated/*.json` — the case schema. Each case has `case_id`, `category`, `feed_messages`,
  `question`, `reference_answer`, `expect_abstention`, and sometimes `variant`.
- `remember_this/agent/runner.py` — `TurnResult` has `.reply` (str), `.tool_called` (str | None), and
  `.cited_memory_ids` (list[int]). This is what a harness run gives you to grade against.
- `evals/harness/collect_outputs.py`'s `_collect_one` — shows the shape of seeding a case and getting a
  `TurnResult` back. Phase 4's runner will do the same thing, then call your four functions on the result.

---

## 1. `verbatim_fidelity(case, turn) -> bool | None`

**What it checks:** when the reference answer is itself a literal value (an id, a code, a password, a
plate number), does `turn.reply` contain that exact string, character for character?

**Why `bool | None` and not just `bool`:** this only makes sense for cases where `reference_answer` *is*
the literal value to reproduce. For an abstention case (`reference_answer` is a sentence like "Nothing
recorded about a hamster") or a borderline-relevance case, there's nothing to check verbatim — return
`None` for "not applicable," not `False` for "failed." A caller that counts failures needs to be able to
tell these apart, or every abstention case will look like a verbatim-fidelity miss.

**How to decide which cases apply:** look at `03_exact_identifiers.json` — every case there has a
`reference_answer` that is purely the identifier itself (`"tH3-0wL_l1v3s"`, `"X4471203"`, `"@nat_wu.88"`).
Several cases in other categories also carry an identifier-shaped reference answer (`csf_01`'s `"ABCDEF"`,
`nd_07`'s `"4417"`). Two ways to decide applicability, pick one and be consistent:

- **By category**: hardcode that `exact_identifiers` always applies, nothing else does. Simple, but misses
  the identifier-bearing cases in other categories.
- **By a heuristic on `reference_answer` itself**: short, no spaces, contains a digit or mixed case — this
  catches more cases but needs tuning so it doesn't misfire on short word-only answers like `"Nobu"` or
  `"4417"` is clearly fine but `"the mac and cheese"` should NOT be run through an exact-substring check in
  a way that penalizes paraphrase (it's prose, not an identifier).

Whichever you choose, write it as a small, named, testable rule — not an inline guess buried in the
function. Something like `_looks_like_identifier(reference_answer: str) -> bool`.

**The check itself**, once applicability is settled:

```python
reference_answer in turn.reply
```

Exact, case-sensitive substring match. Do not lowercase either side, do not strip punctuation — the whole
point of this category is that `tH3-0wL_l1v3s` must not become `the-owl-lives` or `TH3-0WL_L1V3S`.

---

## 2. `abstention_correctness(case, turn) -> bool`

**What it checks:** does `case["expect_abstention"]` match whether the system actually abstained?

**The hard part is detecting abstention from `turn.reply` alone** — there's no structured `abstained`
field on `TurnResult`. Go read the actual phrasing the system is instructed to use:

- `remember_this/llm/prompts/answer.py` — what `generate_answer` is told to say when it can't answer.
- `remember_this/agent/prompt.py` — the top-level agent's rules for relaying a `search_memories` result
  that found nothing (rule 3's phrasing guide).

Pull out the actual fixed phrase(s) the system is instructed to produce (something like "I don't have
anything recorded about...") and match on that, rather than guessing a phrase that sounds plausible but
isn't what the prompts actually say. If the prompts allow some wording variation, you may need 2-3
alternative phrases to match against — keep the list short and anchored to what the prompts literally say,
not a general-purpose "sounds like a refusal" classifier.

**Then the actual comparison:**

```python
actually_abstained = _detect_abstention(turn.reply)
return actually_abstained == case["expect_abstention"]
```

**Edge case worth handling explicitly:** `ab_08`'s category (`near_miss_partial`) and its sibling pattern
in `07_borderline_relevance.json` (the `false_presupposition` variant, e.g. `br_08`) are abstention cases
where a *good* answer still surfaces a related fact (see the correctness judge rubric in
`judges.py`/`judge_prompts.py` — you went through exactly this distinction during judge validation). A
reply like "I only know the appointment is on the 14th, not the time" is a correct abstention and should
still count as `True` here. Don't let your abstention-detection phrase-matching accidentally require a bare
"nothing recorded" with zero other content, or you'll mark a well-formed abstention like that one `False`.

---

## 3. `attribution(turn) -> bool`

**What it checks:** is every id in `turn.cited_memory_ids` legitimate — i.e. not invented?

**The actual constraint, and why it's weaker than it sounds:** `TurnResult` only gives you the final
`cited_memory_ids` from the `Answer` the `search_memories` tool returned. It does **not** give you the
full list of ids `retrieve()` considered before answering — that list exists only transiently inside
`retrieve()`/`check_relevance`, and isn't threaded back through `run_turn`. So you cannot check "is every
cited id among the ids retrieval returned" without adding new plumbing (same tradeoff you already decided
against for Langfuse-trace-based attribution — don't reopen it here for the same reason).

**What you can check without new plumbing**, and it's still a real, useful check:

```python
async def attribution(turn: TurnResult) -> bool | None:
    if turn.tool_called != "search_memories":
        return None  # nothing to attribute on a save turn
    if not turn.cited_memory_ids:
        return True  # abstained or answered with nothing to cite -- nothing to falsify
    rows = await db._get_pool().fetch(
        "SELECT id FROM memories WHERE id = ANY($1)",
        turn.cited_memory_ids,
    )
    return len(rows) == len(turn.cited_memory_ids)
```

This confirms every cited id refers to a memory that actually exists in the database — catches the
specific failure mode of the model inventing a plausible-looking id that was never returned by anything.
It does **not** catch a subtler failure (citing a real id that belongs to a different memory than the one
actually used to answer). Write this limitation into the function's docstring explicitly, so it isn't
mistaken for a stronger guarantee than it is. Revisit this metric specifically if a real failure shows up
that this version can't catch — that's the signal to finally thread `retrieve()`'s candidate ids through
`TurnResult`, not before.

---

## 4. `routing(case, turn) -> bool`

**What it checks:** did the top-level agent call the tool matching what the case expects?

**The mapping is almost entirely mechanical** given `case["expect_abstention"]` and `case["category"]`:

| Case shape | Expected `turn.tool_called` |
|---|---|
| any case that stores facts and then asks a question about them (every category except pure abstention) | `search_memories` for the question turn |
| the seeding turns (storing `feed_messages`) | `save_memories` |

**The subtlety:** `routing` only makes sense for the *question* turn, not the seeding turns — Phase 4's
runner calls `run_turn` once per feed message during seeding and once more for the actual question. Only
the final call's `TurnResult` is what gets passed to this function; seeding's tool calls are already known
to be `save_memories` by construction (that's literally what `seed_case.py` does) and don't need re-
checking here.

**Write it as:**

```python
def routing(turn: TurnResult) -> bool:
    return turn.tool_called == "search_memories"
```

This looks almost too simple, and that's fine — every case in this dataset's question turn should route to
`search_memories`, including every abstention case (abstaining is still a `search_memories` outcome, just
one that found nothing usable). If you ever add a case whose question turn should legitimately route to
`save_memories` or trigger the unclassifiable path, that's when this function needs a per-case expected-
tool field — don't add that complexity before you have a case that needs it.

---

## Pitfalls

- Returning `False` instead of `None` for a metric that doesn't apply to a case will silently inflate your
  failure count and make categories like abstention look worse than they are on verbatim fidelity.
- Don't guess the abstention phrase — read the actual prompts. A plausible-sounding guess that doesn't
  match what the system actually says will misclassify every abstaining case.
- `attribution` as written here is a real but partial check (invented ids only, not wrong-memory
  citations) — say so in the docstring rather than implying it's complete.
- Keep each function pure and synchronous where possible; `attribution` is the only one that needs a
  database call, and it should be the only one.

---

## How to test this file, end to end

Phase 4's full runner doesn't exist yet, so test each function directly against hand-picked cases and
real `TurnResult`s — same pattern as the smoke tests already used earlier in this step (see the manual
`asyncio.run` scripts used to validate `run_turn` and the judges).

1. **Unit-test each function in isolation first**, with a fake `TurnResult` you construct by hand (no
   database, no LLM) — confirm the logic is right before paying for a real run:
   - `verbatim_fidelity`: feed it a case from `03_exact_identifiers.json` and a `TurnResult` whose `.reply`
     contains the exact id — expect `True`. Mutate one character in the fake reply — expect `False`. Feed
     it an abstention case — expect `None`.
   - `abstention_correctness`: construct a `TurnResult` with a reply matching your detected phrase against
     a case with `expect_abstention: true` — expect `True`. Flip either side — expect `False`. Specifically
     test `ab_08`'s shape (abstains on time, but still mentions the 14th) — expect `True`, not `False`.
   - `routing`: trivial, just confirm it reads `tool_called` correctly for both tool names and `None`.
   - `attribution`: this one needs the database for its existence check — test it against a real run (see
     step 2) rather than purely in isolation.

2. **Run each function against one real case per category**, using `seed_case.seed_case` plus `run_turn`
   exactly like `collect_outputs.py` already does — pick one case id from each of the 8 category files,
   seed it, ask its question, and print what each of the four metrics returns. You already have the labels
   in `evals/data/labels/records.json` for 30+5 cases with your own `human_faithfulness`/`human_correctness`
   judgments — cross-check a few of these against what `verbatim_fidelity` and `abstention_correctness`
   say, since you already know by hand whether those specific answers were right.

3. **Specifically re-run the two regression-guard cases** (`br_10` — Nobu category question, should answer
   and route to `search_memories`; `inj_01` — safe code question after an injection attempt, should abstain
   and route to `search_memories`) through all four metrics, since these are the cases most likely to
   expose a metric bug given how unusual their shape is.

4. **Done when**: all four functions have been run against at least one real case per category, every
   `None` case is confirmed to be a genuine not-applicable rather than a missed `False`, and you can state
   in one sentence what `attribution`'s known blind spot is.
