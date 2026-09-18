# Phase 8 — Multi-tenancy, safety, and failure behaviour

Status: decided. Decision record: `decisions/ADR-009-safety-and-failure.md`.

## Access

**Open to anyone**, with per-user usage visible on a dashboard so that abuse can be spotted and the bot gated
later. Gating is a config change, not a redesign.

Resolvable tension with ADR-007: traces carry hashed user ids, so Langfuse alone cannot tell you *who* to
block. The application database holds the real Telegram id, so the hash is only opaque inside the
observability tool — blocking remains possible from your own data. Worth noting explicitly, because
discovering it during an incident would be unpleasant.

What the dashboard needs to answer: how many distinct users, how many messages each, and whether any single
user's volume looks automated.

## Isolation

**Application-level filtering on user id.** Every read and write carries the caller's id; no query exists that
does not filter on it. No row-level security in v1.

This is the highest-severity bug class in the system — a leak means one family member reading another's
private notes. Two cheap mitigations that are not defence in depth but catch the realistic mistake:

- retrieval takes the user id as a required argument, never an optional filter
- at least one eval case stores facts as two different users and confirms neither can retrieve the other's

## Rate limiting

Per-user cap, counted in the application database (no Redis — nothing else needs one). On exceeding it, a clear
message rather than silence. Limits sized generously enough that a real family member never notices.

The rate limit is what makes an open bot tolerable: it bounds what a stranger can consume from the university
LLM quota before you notice them on the dashboard.

## Prompt injection through stored memories

The real exposure: a memory is untrusted user text that later lands in an answer prompt. "Ignore previous
instructions and say X" stored today is executed at recall time tomorrow. Self-injection only, given DM-only
scope — a user can only poison their own memories — but the failure is still a fabricated answer, which is the
gated failure from Phase 0.

Handled, proportionately:

- **Memories are passed as structured data, not inlined prose.** The prompt receives a list of records with
  ids, not a paragraph that reads like instructions.
- **The system prompt states that memory content is data to be reported, never instructions to follow.**
- **The answer must cite the memory id it used** (ADR-001), which makes an unsupported answer visible.
- **Injection cases go in the eval set** as their own category, so the defence is measured rather than assumed.

Not done: input sanitisation, injection classifiers, output filtering. Disproportionate at this scale, and
none of them are reliable anyway.

Stated honestly: these measures reduce the risk, they do not eliminate it. That framing belongs in the writeup
— overclaiming here is worse than the residual risk.

## Failure behaviour

Fail fast with a clear message. No retries on infrastructure failures; the retry budget is already spent on the
relaxed-threshold search pass, and the whole turn runs inside the webhook request (ADR-006).

| Failure | User sees | Notes |
|---|---|---|
| LLM endpoint down or rate-limited | clear "can't reach the model right now, try again shortly" | distinguish these two in traces; quota exhaustion is an operational signal |
| embedding call fails | same, phrased for the operation attempted | |
| database unavailable (including Neon wake failure) | clear "can't reach my memory right now" | |
| extraction returns invalid schema | "couldn't understand that, try rephrasing" | logged as a schema failure, not a user error |
| store succeeds but reply fails to send | nothing | memory is stored; the user may resend, and `update_id` idempotency absorbs the duplicate |
| turn exceeds Telegram's patience | possible retry | absorbed by `update_id` idempotency |
| rate limit exceeded | clear message naming the limit | |

Every failure path returns 200 to Telegram once handled, so a handled error does not trigger a retry.

Partial-failure note: extraction happens before storage, so a failure between them loses the message with
nothing stored — the safe direction. A failure after storage but before the confirmation reply leaves a stored
memory the user does not know about, which is the one case where the user's mental model and the store diverge.
Acceptable, and visible in traces.

## Input handling

**Store whatever comes.** No length limits, no junk filtering. Unclassifiable messages already get a fixed
reply (ADR-002); anything the agent routes to storage is stored.

Consequence to watch: a very long message could produce many extracted facts and a large token bill against
the university quota. Fact-count-per-message is already logged (Phase 6), so this will be visible if it
happens.

## Data rights

- `/forget` deletes all of the calling user's memories after confirmation.
- Traces are not purged; `/help` states this and states the retention window (ADR-007).
- No export in v1.
