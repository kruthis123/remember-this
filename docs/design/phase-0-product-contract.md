# Phase 0 — Product contract

Status: accepted. Decision record: `decisions/ADR-001-scope-and-success.md`.

## What the bot does (v1)

A Telegram DM bot. Two behaviours only:

1. **Store** — user sends a natural-language message containing one or more facts. An LLM extracts
   the fact(s). The bot replies with a confirmation showing what it understood and stored.
2. **Recall** — user asks a question. The bot answers from stored memories, or states that it has
   nothing relevant.

Recall is **point lookup only**: every in-scope question is answerable from a single stored memory.

## Committed example interactions

Queries are paraphrase-varied on purpose; each stored fact has several valid phrasings.

| # | Store | Recall | Expected answer |
|---|---|---|---|
| 1 | "The name of the new burrito place I want to try is Guzman y Gomez" | "What is the name of the burrito place I want to try" / "what was that Mexican place called?" | Guzman y Gomez, spelled exactly |
| 2 | "My student id is ABCDEF" | "What is my student id" | ABCDEF, exact case |
| 3 | "I did not like the mac and cheese at Rosetta's" | "What did I not like at Rosetta's" | the mac and cheese |
| 4 | "My final exam ends on Nov 30th" | "When is my exam ending" / "when do my finals finish" | Nov 30 (any equivalent date phrasing) |
| 5 | multi-fact: "just got back from Guzman y Gomez, burrito was solid but the mac and cheese was awful, and my exam ends Nov 30" | any of the above | each fact independently recallable |
| 6 | *nothing stored about the dentist* | "What's the dentist's address" | explicit "nothing recorded about that" |

## Definition of a correct answer

All four must hold:

1. **Grounded** — every claim in the answer traces to a retrieved memory. No invented detail.
2. **Verbatim where it matters** — identifiers, proper nouns, and codes reproduced exactly,
   including case. Semantic paraphrase is acceptable everywhere else.
3. **Responsive** — answers the question asked, not an adjacent one.
4. **Honest about absence** — when no relevant memory exists, says so rather than answering. When one
   does exist, abstaining is a failure.
5. **Attributed** — the answer cites the memory it came from, including when it was recorded, so the
   user can verify it themselves.

A **wrong answer** is any of: a fabricated or corrupted value, an answer drawn from a memory that
doesn't address the question, or a claim of ignorance when the memory was present and retrievable.

## Failure preference (release gate)

Latency is the only freely tradeable dimension. Both correctness failures are gated.

1. **Confidently wrong** — unacceptable. The failure the system is designed against.
2. **False "I don't know"** — also unacceptable. Abstaining when the memory was present and
   retrievable is a bug, not a safe fallback.
3. **Slow** — acceptable without limit within reason. Measured and reported, never traded against
   either correctness failure.

Consequence: the system may spend as many LLM calls and seconds as it needs — retry, re-query,
verify — to avoid both fabricating and giving up prematurely. "I don't know" is only correct when
nothing relevant exists. Releases are gated on both fabrication rate and false-abstention rate, since
either can be driven to zero at the other's expense.

## Non-goals (v1)

Deferred, in rough priority order for later phases:

- Latest-value lookup (contradicting/superseding memories)
- Aggregate and scan queries ("how much did I spend", "what did I say about X")
- Yes/no questions — deferred because absence of a memory is not evidence of the negative, and
  handling that distinction properly is its own design problem
- Proactive messages: reminders, nudges, on-this-day
- Group chats
- Non-English and mixed-language input
- Explicit edit/delete of a stored memory beyond a basic delete-all
- Voice, images, files, forwarded messages

## Scale and quality assumptions

- Users: a handful of trusted family members, DM only.
- Corpus: hundreds of memories per user within months.
- A vector index is in scope regardless of whether hundreds of rows strictly require one — it is a
  study goal (see ADR-001).
- Distractor density is the main source of eval difficulty; the eval set must simulate a populated
  store, not five clean facts.

## Eval-first commitment

The eval harness and a hand-written dataset are built **before** the bot works end to end. No prompt
or retrieval change ships without an eval run. This ordering is a deliberate constraint, recorded
here so that abandoning it later is a visible decision rather than a drift.

## Eval surface this contract creates

| Layer | What is judged | Method |
|---|---|---|
| Write path | extraction correctness and completeness from messy multi-fact input | rubric + LLM judge |
| Retrieval | relevance of retrieved memories to the question | recall@k on labelled ids + LLM-judged relevance |
| Answer | faithfulness to retrieved memories (no invented detail) | LLM judge |
| Answer | correctness against reference answer, paraphrase-tolerant | LLM judge |
| Answer | exact reproduction of identifiers and proper nouns | deterministic assertion |
| Abstention | was refusing appropriate; was answering appropriate | LLM judge |
| Attribution | cited memory is the one actually used and supports the answer | deterministic id check + LLM judge |
| Meta | judge agreement with hand labels | human-labelled subset, agreement stat |
