# Phase 1 — Interaction and intent model

Status: decided. Decision record: `decisions/ADR-002-intent-model.md`.

## Message taxonomy

Every inbound text message resolves to exactly one of:

| Category | Handling |
|---|---|
| **Feed** — contains fact(s) to store | extract, store, reply with confirmation of what was understood |
| **Question** — asks about stored memories | retrieve, answer with attribution, or state nothing is recorded |
| **Ambiguous** — plausibly either | ask the user which they meant |
| **Unclassifiable** — neither (greetings, chatter, noise) | fixed reply: "I'm sorry, I did not get that" |
| **Command** — `/start`, `/help`, `/forget` | deterministic handler, no LLM |

## Locked decisions

**Classification is LLM-inferred.** No command needed to store or recall. Natural language only.
Commands exist solely for administrative actions.

**Ambiguity triggers a clarifying question.** The bot does not guess between feed and question. This
follows directly from the Phase 0 failure preference: a wrong guess produces either a fabricated
answer or a silently mis-stored memory, both gated failures, while a clarifying question only costs
the user a tap.

**Each message is standalone.** No conversational context carried across messages. A question is
answered against the memory store alone, never against preceding chat. Consequence: follow-ups like
"and what about the mac and cheese?" are out of scope and will land as unclassifiable or be answered
poorly. Accepted, consistent with point-lookup scope.

**Unclassifiable gets a fixed non-LLM response.** No attempt to be conversational.

**Commands in v1:** `/start`, `/help`, `/forget`. No `/list` — it exercises no skill this project
targets.

## Where classification lives — resolved in Phase 4

No separate classifier call. The agent's tool choice *is* the classification (ADR-005): `save_memories`
means feed, `search_memories` means question, `request_clarification` means ambiguous. Routing stays
independently measurable because the chosen tool is logged as the intent label.

Rejected: a dedicated classification call (cleaner spans, one more call and one more failure point), and
a single structured call returning intent plus extraction together (couples two failure modes).

## Clarification round trip — inline keyboard buttons

The clarifying reply carries two buttons ("Save this" / "Answer this"). The callback payload references
the original message, so no server-side pending state is needed and statelessness holds. The same
mechanism serves the `/forget` confirmation.

Two benefits beyond simplicity: the user's tap is an unambiguous signal rather than another message to
classify, and it is a free ground-truth label for a case the classifier found hard — directly useful for
the Phase 7 dataset.

Rejected: short-lived pending state keyed by user id (needs a state store and an expiry rule, and
reintroduces the conversational context otherwise excluded), and asking the user to resend with a command
prefix (simplest, worst experience).

## Command semantics

- `/start` — greeting and one-line explanation.
- `/help` — what the bot does, with examples. Static text.
- `/forget` — deletes **all** of the calling user's memories, after an explicit confirmation step. No
  selective deletion in v1, which keeps Phase 2 free to choose an append-only model if it wants.
  Open: whether it also purges observability traces — decide in Phase 6 against `constraints.md` C6,
  since a delete that leaves the content sitting in a trace store contradicts the stated posture.

The confirmation step needs the same message-to-message continuity as the clarification path above.
One mechanism should serve both; that is a point in favour of the inline-keyboard option.

## What must be logged for Phase 6

- classified intent and, if available, confidence
- whether clarification was triggered, and what the user chose
- unclassifiable-response rate

Routing is the first place quality is lost, and it is invisible without these.
