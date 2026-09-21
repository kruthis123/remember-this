# Step 4 — Retrieval

Files you will write: `remember_this/retrieval/embeddings.py`, `remember_this/retrieval/search.py`, and
`remember_this/llm/prompts/relevance.py` + `remember_this/llm/relevance.py`.

Design references: ADR-004 and `phase-3-retrieval.md` (the whole pipeline and retry semantics), ADR-005
(relevance check is a non-tool structured call, same pattern as extraction).

You already have `search_memories(user_id, query_embedding, threshold, limit)` in `repository.py` from step
2 — this step is about producing the `query_embedding`, orchestrating the strict → relaxed → relevance-check
sequence, and building the relevance check itself. No new database work.

---

## Part 0 — Concepts you need first

### Getting an embedding

Your embedding model, `bge-m3`, is served through the same OpenAI-compatible endpoint as chat, just a
different API surface: the `/embeddings` endpoint rather than `/chat/completions`. Pydantic AI's `Agent`
abstraction is for chat models with structured output — it is not the tool for embeddings. Use the `openai`
Python client directly here, pointed at the same `base_url`/`api_key` as your chat client.

Look up `AsyncOpenAI(...).embeddings.create(model=..., input=...)`. It's a single call, no agent, no
structured output involved — the response is just a list of floats per input string.

Two things to get right:

- **Reuse one client**, don't construct a new `AsyncOpenAI` per call. Same reasoning as building the
  Pydantic AI agent once in `client.py` — construction has overhead you don't want to repeat per request.
- **The vector dimension must be exactly 1024** to match your `vector(1024)` column (C7 / step 2). If
  `bge-m3` ever returns something else — some embedding APIs let you request a reduced dimension — your
  insert will fail loudly. Print `len(embedding)` the first time you call this and confirm it's 1024 before
  building anything on top.

### Why the relevance check is a separate structured call, not a tool

Same reasoning as extraction in step 3: the agent (step 6) should not be able to choose whether to run the
relevance check on a relaxed-threshold retry — it always runs, or abstention loses its guardrail. Build it
now, standalone and directly callable, exactly like `extract_facts`.

### The shape of what you're orchestrating

Re-read the pipeline in `phase-3-retrieval.md` before writing code — this is the diagram you're implementing:

```
question
  → embed verbatim
  → search at strict threshold
  → if results: done, answer from these
  → if empty: search again at relaxed threshold
      → if still empty: abstain
      → if results: relevance check on these specific candidates
          → check says yes: answer from these
          → check says no: abstain
```

Note precisely when the relevance check runs: **only** on the relaxed-threshold path, and only when that
path actually returned candidates. A strict-threshold hit skips the check entirely — it's cheap-gate,
expensive-gate, not expensive-gate-always.

---

## Part 1 — `retrieval/embeddings.py`

Write one function:

```python
async def embed_text(text: str) -> list[float]:
    ...
```

Construct the `AsyncOpenAI` client once at module load, same pattern as `client.py`'s `_provider`. Pull
`embedding_model` from settings rather than hardcoding `"bge-m3"` — you already have the config field.

Decide: does this function embed one string, or should it also support a batch (`list[str] -> list[list[float]]`)? You don't strictly need batching yet — questions are embedded one at a time — but step 8's
distractor corpus generation will need to embed a few hundred facts, and doing that one at a time will be
slow and wasteful of round trips. Consider writing the batched version now and having the single-string case
call it with a list of one, rather than writing both separately and maintaining two code paths.

---

## Part 2 — the relevance check

### The contract

Input: the question, and the list of candidate facts (just the text, not full `MemoryMatch` objects — the
model doesn't need ids or timestamps to judge relevance, and passing them invites the model to reason about
irrelevant details).

Output, a Pydantic model:

```python
class RelevanceVerdict(BaseModel):
    can_answer: bool
    reasoning: str
```

Why include `reasoning` even though nothing shows it to the user: `phase-3-retrieval.md` requires the
verdict's reasoning to be logged (Phase 6), and it is also exactly the kind of field that makes debugging a
false abstention or a fabrication tractable later. Free to add now, expensive to retrofit into a trace
format later.

Decide: verdict per-candidate, or one verdict for the whole candidate set? `phase-3-retrieval.md` phrases it
as "can the question be answered from **any** of this" — a single set-level verdict matches that framing and
is simpler. A per-candidate verdict would let you drop some candidates and keep others, which is more
precise but is not what the design calls for. Default to the single verdict unless you have a reason not to.

### The prompt

New file, `remember_this/llm/prompts/relevance.py`. This prompt has a narrower job than extraction's, but
get the framing exactly right, because this is explicitly your guardrail against fabrication on weak
retrieval (`phase-3-retrieval.md`: "the relevance check is a guardrail in its own right").

The critical distinction to state explicitly, because it's the one place a model naturally drifts: **"is this
topically related" is not the question.** The question is "can this specific question be answered from this
specific content." A memory about Domino's garlic bread is topically related to "what pizza places have I
been to" but does not answer it. Give the prompt at least one example of a topically-close-but-non-answering
case, not just an obviously-relevant and an obviously-irrelevant one — the boundary case is the one that
actually tests the guardrail.

Apply the same prompt-engineering approach from step 3: role, task definition stated as a rule (not a vibe),
the one instruction that matters most given its own weight, then examples that confirm the rule rather than
substitute for it.

### The function

`remember_this/llm/relevance.py`, mirroring `extraction.py`'s shape:

```python
async def check_relevance(question: str, candidate_facts: list[str]) -> RelevanceVerdict:
    ...
```

Build the agent once at module load using `create_agent`, same as extraction. Decide what to return if
`candidate_facts` is empty — should this function even be callable with no candidates, or should the caller
(the search orchestration in Part 3) simply never call it in that case? The pipeline diagram implies the
latter: an empty relaxed search should abstain directly, without invoking the relevance check at all.

---

## Part 3 — `retrieval/search.py`

This is the orchestration function that implements the full diagram. Design the return type first — you
need it to distinguish three outcomes, not two:

- answered, with the memories to answer from
- abstain, no candidates found at all
- abstain, candidates found but the relevance check rejected them

Something like:

```python
class RetrievalOutcome(BaseModel):
    matches: list[MemoryMatch]
    abstain: bool
    retry_occurred: bool
    relevance_verdict: RelevanceVerdict | None
```

The last two fields exist because `phase-3-retrieval.md` requires logging "whether a retry happened" and
"the relevance check's verdict and reasoning" — decide the shape now so step 7's tracing has something
consistent to read, rather than reconstructing this from ad-hoc booleans later.

The function:

```python
async def retrieve(user_id: int, question: str) -> RetrievalOutcome:
    ...
```

Steps inside it, matching the diagram exactly:

1. Embed the question (once — the query is never re-embedded differently between passes, since it's never
   rewritten).
2. Search at `settings.strict_threshold`.
3. If non-empty, return immediately: answered, no retry, no relevance verdict needed.
4. If empty, search again at `settings.relaxed_threshold`.
5. If that's also empty, return: abstain, retry occurred, no candidates to check.
6. If non-empty, call `check_relevance` with the candidates' fact text.
7. Branch on the verdict: `can_answer=True` returns the candidates as matches; `can_answer=False` returns
   abstain with the verdict attached (so the trace shows *why* it abstained despite finding something).

Note step 4's `limit` argument — you built `search_memories` to take one, but this design's threshold does
the real filtering, so what should `limit` be here? `phase-3-retrieval.md` calls it "a hard cap... sized
generously enough that it never becomes the effective selector" — pick a number like 20 and put it in
config rather than hardcoding it inline, since it's a tuning knob just like the thresholds.

---

## Pitfalls

- Don't call the relevance check on strict-threshold hits. It only exists for the relaxed-threshold path —
  calling it always would silently double your LLM calls per turn for no benefit and contradicts the
  documented "cheap gate, expensive gate" design.
- Don't re-embed the question between the strict and relaxed passes. Only the threshold changes.
- Verify the embedding dimension is 1024 the first time you call `embed_text`, before wiring it into
  search — a silent mismatch here fails at the database insert, several layers away from the actual cause.
- The relevance check's prompt needs a topically-close-but-wrong example, not just clear-cut cases, or it
  won't actually test the boundary it exists to guard.
- `retrieve()`'s three-way outcome (answered / abstain-empty / abstain-rejected) matters for Phase 7's
  metrics, which read retrieval and abstention together — don't collapse it down to a plain boolean.

## Done when

- `embed_text` returns a 1024-length vector for a sample string, confirmed by printing its length.
- A strict-threshold hit on an obvious question (e.g. re-run one of step 3's stored facts through search)
  returns answered, with no relevance check invoked — check this by adding a temporary print inside
  `check_relevance` and confirming it never fires on this case.
- A question with nothing remotely related stored returns abstain, with `retry_occurred=True` and
  `relevance_verdict=None`.
- A genuinely borderline case — something topically close but not actually answering the question — reaches
  the relevance check and you can inspect its `reasoning` to see whether the verdict is sound.
- You can state, in one sentence, what `limit` is for in `search_memories` given that the threshold is
  doing the real filtering.
