# Phase 2 — Memory representation

Status: decided. Decision record: `decisions/ADR-003-memory-representation.md`.

## Two record types

**Message** — the raw inbound text, verbatim, exactly as sent. Never rewritten.

**Memory** — one atomic fact extracted by the LLM from a message. A message with three facts produces
three memories, each independently retrievable, each pointing back to its source message.

Fields, semantically (not a schema definition):

| Record | Field | Purpose |
|---|---|---|
| Message | id | referenced by memories |
| Message | user id | ownership and isolation (Phase 8) |
| Message | raw text | verbatim original; debugging and extraction eval baseline |
| Message | received at | source of the date shown in answer attribution |
| Memory | id | cited in answers, referenced in eval labels |
| Memory | user id | every retrieval filters on this |
| Memory | fact text | the extracted statement; what gets embedded and searched |
| Memory | source message id | links back to the raw text |
| Memory | created at | attribution, and ordering if latest-value is added later |

No LLM-derived metadata: no entities, no tags, no topics, no confidence scores. Timestamps and user
ids are structural, not extracted.

## Locked decisions and why

**Keep both raw and extracted.** The raw message is the ground truth for judging extraction, and the
only way to answer "did the model drop or distort something" after the fact. Cheap at hundreds of rows.

**Split into atomic facts.** Required by contract example 5 — a rambling three-fact message has to be
recallable fact by fact. Also makes retrieval units small and focused, which helps precision.

**Extraction is synchronous, before the reply.** Follows from the confirmation requirement: the user
must see what was understood. Costs latency, which Phase 0 declared free.

**Append-only.** No updates, no selective deletes. `/forget` wipes everything. Nothing in v1 needs
mutation, and append-only keeps the audit trail intact for debugging.

**Contradictions are stored side by side.** No detection, no warning, no supersession. Recall may
return a stale fact.

## The accepted hole, stated plainly

Storing contradictions without resolution means a stale answer is possible, and a stale answer is a
confidently wrong answer — the exact failure Phase 0 gates on. These two decisions are in tension.

The resolution is scoping, not engineering: latest-value cases are a declared non-goal, so they must
be **excluded from the v1 eval set**. Otherwise the release gate fails on a limitation that was
chosen deliberately. This must be explicit in Phase 7, or the eval will either be quietly rigged or
permanently red.

Consequence to respect: nothing here may make supersession impossible to add later. `created_at` on
every memory and an intact raw-message trail are what keep that door open.

## Consequences of no metadata

Retrieval in Phase 3 is purely semantic over fact text. No filtering, no hybrid keyword-plus-tag
scheme, no date-range narrowing. That is a real constraint on Phase 3, and it is the first thing to
revisit if recall turns out to be the weak link — which is exactly what the retrieval metrics are
there to reveal.

## What must be logged for Phase 6

- raw message alongside every extracted fact, so extraction is inspectable per trace
- number of facts extracted per message
- extraction latency and token count
- memory ids returned by retrieval, so answers can be traced to sources
