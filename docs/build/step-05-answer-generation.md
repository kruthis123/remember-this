# Step 5 — Answer generation

Files you will write: `remember_this/llm/prompts/answer.py`, `remember_this/llm/answer.py`.

Design references: ADR-005 (answer generation is a non-tool structured call, same family as extraction and
relevance), `phase-0-product-contract.md` (the definition of a correct answer — this is the step that has
to actually deliver it), ADR-001/`phase-0-product-contract.md`'s failure preference (fabrication and false
abstention are both gated; there is no acceptable middle ground).

This is the last LLM step before step 6 wires everything into the actual agent. After this, `retrieve()`
from step 4 and `answer()` from this step compose into the full recall path.

---

## Part 0 — What this step is actually for

Re-read the product contract's five correctness requirements before writing anything — this prompt has to
satisfy all five simultaneously, and each one maps to something concrete you have to build in:

1. **Grounded** — nothing in the answer beyond what the retrieved facts state.
2. **Verbatim where it matters** — same rule as extraction, now on the output side. If a retrieved fact says
   `ABCDEF`, the answer must say `ABCDEF`, not `abcdef` or "your student ID."
3. **Responsive** — answers the actual question, not a related one the retrieved facts happen to support.
4. **Honest about absence** — but note: by the time this function is called, `retrieve()` has *already*
   decided whether to abstain (step 4's strict/relaxed/relevance-check pipeline). This function does not
   re-decide abstention from scratch — more on this below, it's the most important design decision in this
   step.
5. **Attributed** — cites which memory the answer came from, and when it was recorded.

### The abstention boundary you need to get right

`retrieve()` already returns `RetrievalOutcome.abstain` as a bool. Given that, does `answer()` even get
called when `abstain=True`? Two designs:

- **Caller checks `abstain` first; `answer()` is only ever called with real matches.** Simpler. `answer()`
  never needs to produce an abstention response itself — the caller (step 6's agent, or your test script for
  now) handles the "nothing recorded about that" reply directly, without an LLM call. Cheaper, and it means
  this function has one job: answer from facts that are already known to exist.
- **`answer()` always gets called, with `matches` possibly empty, and decides itself whether to abstain.**
  This duplicates the abstention decision `retrieve()` already made, in a second place, using a second
  model call. It also reopens a question step 4 already closed: `phase-3-retrieval.md`'s relevance check
  exists specifically so this decision doesn't have to be remade at answer time.

Pick the first. Re-deciding abstention here would mean two different components can each independently
decide to abstain for different reasons, and a false abstention becomes harder to diagnose because you
won't know which of the two decided it. Keep the responsibility in exactly one place.

This does mean `answer()`'s contract simplifies to: **you will always be given at least one relevant
match.** Write it with that assumption, and let the caller be responsible for the empty case entirely.

---

## Part 1 — The contract

### Input

The question, and the matches to answer from. Decide: pass `list[MemoryMatch]` directly (id, fact_text,
created_at, similarity), or extract just the fields the prompt needs? Passing the full `MemoryMatch` is
reasonable here — unlike the relevance check, this step *does* need the id (for citation) and the timestamp
(for "when it was recorded"), so there's no reason to strip fields the way `check_relevance` stripped
candidates down to bare text.

### Output

A Pydantic model. Design it to make attribution structural, not something the model has to remember to
mention in prose:

```python
class Answer(BaseModel):
    answer_text: str
    cited_memory_ids: list[int]
```

Why `cited_memory_ids` as a separate field rather than expecting the model to work a citation into
`answer_text` and parsing it back out: it's directly checkable. `phase-0-product-contract.md`'s eval surface
lists "cited memory is the one actually used and supports the answer" as a deterministic id check — that
only works cleanly if the id is a structured field, not something you'd have to regex out of prose.

Decide: does `answer_text` include the date itself (e.g. "you told me on Sep 3 that..."), or does the date
stay purely metadata attached via `cited_memory_ids` and get rendered by whatever calls this later (e.g. the
Telegram handler in step 9)? Either is defensible. If you want the model to weave the date into the answer
naturally, it needs the date in its input and an instruction to use it; if you'd rather render it
consistently in code, keep the prompt focused on the answer content only and format the citation separately
downstream. This affects how much the prompt needs to instruct versus how much later code needs to do.

---

## Part 2 — The prompt

Same structure discipline as steps 3 and 4: role, task rule, the highest-stakes instruction isolated, then
examples that confirm the rules.

Rules this prompt needs, each mapping to one of the five correctness requirements:

1. **Grounding rule.** Answer only using the provided facts. Do not add, infer beyond what's stated, or use
   outside knowledge — note this is a *stricter* rule than the relevance check's rule 2a. The relevance
   check was allowed one bounded common-sense inference to decide whether facts are worth using at all.
   Answer generation should not need to make that same kind of inferential leap to actually *state* the
   answer — if the answer requires inference beyond what the matched facts say outright, that is a signal
   the match was a `can_answer=true, via inference` case, and the answer must make the inference visible
   rather than presenting it as a stated fact. Decide explicitly whether you want to allow this "carry the
   inference into the answer" behavior or require the answer to hedge language when it's inference-based
   (e.g. "you visited Domino's, which is known for pizza" vs. flatly "you had pizza"). This is a real
   decision the design docs don't make for you — make it here and record it.

2. **Verbatim rule.** Identical framing to extraction's rule 1: identifiers, proper nouns, codes, and dates
   copied character-for-character from the matched facts, no reformatting.

3. **Responsiveness rule.** If multiple facts are provided (a multi-fact recall case, or several
   near-duplicate matches), answer only what was asked, not everything provided. Give an example with two
   matched facts where only one is actually responsive to the question, to test whether the model dumps
   both or picks correctly.

4. **Citation rule.** Every answer must include the ids of the facts actually used, and only those — not
   every id it was given. This is where a sloppy model will just echo all input ids back regardless of
   relevance; write a rule against that explicitly and test for it.

### Examples

Use your own contract examples from `phase-0-product-contract.md` as the primary worked cases — you already
have expected answers for all of them. At minimum:

- A single-match case (contract example 2: student id).
- A case with two provided matches where only one is responsive (tests rule 3 and the citation rule
  together — the unused match's id must not appear in `cited_memory_ids`).
- A case exercising verbatim fidelity on something case-sensitive.
- If you decided to allow inference-based answers in rule 1, include one example showing how the answer
  should be phrased when the underlying match required the relevance check's inference allowance (e.g. a
  Domino's/pizza-places case) — this is the one place the two prompts' behaviors have to visibly agree with
  each other.

---

## Part 3 — The function

Same shape as `extract_facts` and `check_relevance`:

```python
async def generate_answer(question: str, matches: list[MemoryMatch]) -> Answer:
    ...
```

Build the agent once at module load via `create_agent`, matching the pattern in `extraction.py` and
`relevance.py` (including passing `temperature` — check what value you settled on for the other two and
decide if answer generation should match it or be lower, given this is the step users actually see).

Decide what happens if `matches` is empty when this is called — per Part 0, this shouldn't happen if the
caller checks `abstain` first, but should the function guard against it anyway (raise, rather than silently
calling the LLM with nothing to work from)? An assertion or explicit `ValueError` here is cheap insurance
against the caller contract being violated later, in step 6, when there are more moving pieces to get wrong.

---

## Pitfalls

- Don't let this function re-decide abstention. That decision belongs to `retrieve()` alone.
- Watch specifically for the model echoing back citation ids it didn't actually use — this is the most
  likely silent failure mode, and it directly breaks the deterministic attribution check in the eval design.
- The grounding rule here is stricter than the relevance check's inference allowance — decide explicitly
  whether/how inference-based matches get worded in the final answer, don't leave it implicit.
- Verbatim fidelity has to survive a second LLM hop now (extraction preserved it into storage; this step has
  to preserve it again out of storage). Test an identifier end to end, not just at each step in isolation.

## Done when

- `generate_answer` on a single-match contract example (student id) returns the id verbatim and cites
  exactly one memory id.
- A two-match case where only one match is responsive returns an answer using only that one, with
  `cited_memory_ids` containing only its id.
- You can state, in one sentence, what happens today if `generate_answer` is called with an empty
  `matches` list.
- You can state, in one sentence, how an inference-based match (accepted by the relevance check via rule 2a)
  gets worded in the final answer, and why you chose that.
- A full path — `retrieve()` then `generate_answer()` on its matches — run together on at least one contract
  example, producing a final answer with correct text and correct citation.
