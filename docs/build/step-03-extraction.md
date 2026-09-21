# Step 3 — Extraction

Files you will write: `remember_this/llm/client.py`, `remember_this/llm/prompts/extraction.py`,
`remember_this/llm/extraction.py`.

Design references: ADR-003 (what a memory is), ADR-005 (structured output everywhere, extraction as a
non-tool call), `phase-2-memory-representation.md`.

This is the first step that talks to the LLM at all, so it introduces Pydantic AI itself, not just the
extraction logic.

---

## Part 0 — Concepts you need first

### What Pydantic AI actually gives you

At its core, a Pydantic AI `Agent` is a wrapper around "call a model, optionally with tools, and get back a
value of a type you specified" — with retries, validation, and tracing hooks built in. You already chose it
in ADR-005 specifically because typed output is its central feature.

The two pieces you need for extraction, and only these — no tools yet, that's step 6:

- `Agent(model, output_type=SomeModel, system_prompt=...)` — construct once.
- `await agent.run(user_prompt)` — returns a `RunResult`; `.output` holds an instance of `SomeModel`,
  already validated.

There is no manual JSON parsing anywhere in your code. Pydantic AI asks the model for structured output (via
whatever mechanism the model supports — see the gotcha below) and validates the response against your
Pydantic model before handing it back. If validation fails, Pydantic AI itself retries automatically a
limited number of times, feeding the model its own validation error. You should still handle the case where
it exhausts retries and still fails — that's a real failure mode, not a bug.

### Why extraction is not a tool

Re-read the distinction in `phase-4-control-flow.md`: tools are for things the *agent* decides whether to do.
Extraction always has to run on a feed message — there is no scenario where storing a fact means skipping
extraction. So it is written as its own function that calls its own `Agent`, called directly from wherever
the routing agent decides "this is a feed message" (step 6 will wire that up). For now, you're building and
testing it standalone.

### Connecting Pydantic AI to your university endpoint

Pydantic AI's model classes assume specific providers by default. To point at an arbitrary OpenAI-compatible
endpoint, you construct the pieces explicitly rather than using a shorthand string:

- `pydantic_ai.models.openai.OpenAIChatModel` — the model wrapper Pydantic AI uses to talk to any
  Chat-Completions-compatible API.
- `pydantic_ai.providers.openai.OpenAIProvider` — takes your `base_url` and `api_key` and hands them to the
  model. This is the piece that redirects requests away from `api.openai.com` and at your university's URL.

You construct a `Provider`, pass it into the `Model`, pass the `Model` into the `Agent`. Look up the current
Pydantic AI docs for the exact import paths and constructor arguments — they move between versions, and
it's better you read them directly than have me guess at a version I haven't confirmed against your
`pyproject.toml`.

Build `remember_this/llm/client.py` to hold this construction, parameterized by `get_settings()`, so every
other module just imports a ready-made model object rather than repeating provider setup. Since three
different roles (system, judge, generator) need three different models pointed at the same base URL, design
this as a function that takes a model name and returns a configured `Agent`-ready model, not a single
hardcoded instance.

### The structured-output gotcha you flagged in C7

Nothing in the model list advertised function-calling or JSON-schema support explicitly. Pydantic AI has two
strategies for getting structured output out of a model:

- **Native structured output / tool-calling mode** — if the backend supports OpenAI's `tools` or
  `response_format` parameter, Pydantic AI uses it directly.
- **Prompted fallback** — if not, Pydantic AI (depending on version) can fall back to asking for JSON in the
  prompt and parsing the response text.

**Do this before writing any extraction logic**: write a five-line throwaway script that builds an `Agent`
with a trivial `output_type` (e.g. a model with one string field) against `qwen3.6:35b` and runs it. If it
returns a validated object, you have your answer and can move on. If it raises immediately, capture the
error — it will usually tell you whether the endpoint rejected `tools`/`response_format`, which tells you
whether you need to look into Pydantic AI's fallback settings. Do not assume; check first. This is exactly
the kind of thing that is cheap to verify now and expensive to discover mid-way through step 6.

---

## Part 1 — The extraction contract

### What extraction takes in and returns

Input: the raw message text (a string). Nothing else — no conversation history (Phase 1: stateless turns).

Output: design a Pydantic model, something like:

```python
class ExtractedFact(BaseModel):
    fact_text: str

class ExtractionResult(BaseModel):
    facts: list[ExtractedFact]
```

Why a wrapper around a list rather than returning `list[ExtractedFact]` directly as the `output_type`: it
gives you a place to add fields later (e.g. a rejection reason) without changing the top-level shape, and
some structured-output mechanisms handle a top-level object more reliably than a bare list. Not load-bearing
either way — your call.

Decide: should `ExtractedFact` carry anything besides text? ADR-003 was explicit — **no LLM-derived metadata**
in the stored `Memory` record. Keep the extraction output equally minimal; anything beyond `fact_text` here
would need a justification the design docs don't give you.

### The prompt

Put it in `remember_this/llm/prompts/extraction.py` as a constant string (ADR-005: prompts live in code,
versioned in git). This is the first prompt in the project, and it directly determines your Phase 7
extraction-quality metric, so it's worth being deliberate rather than terse.

It needs to instruct the model to:

- Split the message into **atomic** facts — one self-contained statement per fact. This is the hard part to
  phrase well. "Guzman y Gomez burrito was great but the mac and cheese was bad, exam ends Nov 30" must
  become three separate facts, not one blob and not five over-fragmented ones.
  Include a worked example in the prompt itself (few-shot) — for a task this specific, one clear example
  usually outperforms a longer abstract instruction.
- Preserve wording that matters. Identifiers, names, and dates must be copied verbatim, not paraphrased —
  this is what your Phase 7 verbatim-fidelity metric checks, and if the extraction step silently
  "cleans up" `ABCDEF` into `Abcdef` there is nothing downstream that can fix it.
- Return nothing (an empty list) if the message contains no storable fact. This matters once step 6 exists,
  where the agent may occasionally reach extraction on a borderline message.
- Not invent, infer, or add anything not present in the message. This is the same faithfulness principle
  Phase 7 checks on the *answer* step — it applies here too, just less obviously, and an eval case should
  exist for it (a message with vague or missing information should not produce a confidently invented fact).

### The function

`remember_this/llm/extraction.py`, roughly:

```python
async def extract_facts(raw_text: str) -> ExtractionResult:
    ...
```

Build the `Agent` once at module load (not per call — construction has some cost, and Pydantic AI is
designed around reusing agent instances), call `.run()` inside the function, return `.output`.

Decide what happens when Pydantic AI's own retries are exhausted and it still can't produce valid output.
Options: let the exception propagate (Phase 8's failure-handling table already has "extraction returns
invalid schema" as a case — this is where that gets implemented), or catch it here and return an empty
`ExtractionResult`. Propagating is more honest, since a silent empty result is indistinguishable from "the
message genuinely had nothing to store."

---

## Part 2 — Testing it standalone

You have no bot and no agent wiring yet — that's fine, this step doesn't need them. Write a throwaway script
(same pattern as `scripts/smoke_test_repository.py`) that:

1. Calls `extract_facts` on each of the contract examples from `phase-0-product-contract.md` — including the
   multi-fact one — and prints the result.
2. Calls it on a message with nothing storable (e.g. "thanks!") and confirms you get an empty list, not a
   fabricated fact.
3. Calls it on a message with an identifier (`"my student id is ABCDEF"`) and confirms the case is preserved
   exactly in the output.

This is manual inspection, not the real eval harness — that's step 8, and it needs the dataset and metrics
from Phase 7 to mean anything. Right now you're just confirming the plumbing works and the prompt isn't
obviously broken before you build anything on top of it.

---

## Pitfalls

- Verify structured-output support against your actual endpoint before writing the extraction logic, not
  after something mysteriously fails.
- Don't let the prompt drift toward "extract the most important fact" — the contract requires *every* fact
  to become its own memory, or example 5 (the multi-fact message) breaks by design.
- Watch for over-splitting too: "the mac and cheese was bad" split into "mac" + "cheese was bad" is a real
  failure mode worth checking for by hand.
- Case sensitivity is easy to lose without noticing, since it "looks fine" in casual review. Test it
  explicitly.
- If the model is verbose (Qwen models can pad output with explanation despite structured-output mode),
  check whether Pydantic AI's validation is actually enforcing the schema or your `ExtractionResult` is
  quietly accepting extra noise somewhere.

## Done when

- The five-line structured-output probe against `qwen3.6:35b` succeeds, and you know which mode (native or
  fallback) is in play.
- `extract_facts` on the multi-fact contract example returns three separate, individually sensible facts.
- `extract_facts` on a message with no storable content returns an empty list, not an invented fact.
- `extract_facts` on the student-id example preserves `ABCDEF` with case intact.
- You can state, in one sentence, what happens in your code today if extraction fails schema validation even
  after Pydantic AI's internal retries.
