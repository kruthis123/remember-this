# Step 9 — Telegram bot

Design references to have open while working through this: ADR-006 and `docs/design/phase-5-infrastructure.md`
(webhook handling, idempotency, the whole-turn-inside-the-request constraint), ADR-009 and
`docs/design/phase-8-safety-and-failure.md` (access, rate limiting, the failure table — this is the literal
spec for Part 5 below), `docs/design/phase-1-interaction-model.md` (commands, the still-unresolved
clarification mechanism), ADR-002's amendment (clarification deferred — do not resurrect it this step).

Everything this step needs on the agent side already exists: `remember_this/agent/runner.py`'s `run_turn`
is the single entry point, and it already does extraction/retrieval/answering/tracing/hashing. Everything
this step needs on the data side already exists too — confirmed by reading `remember_this/db/repository.py`
and `remember_this/db/schema.sql` directly: `claim_update`, `record_turn`, `count_recent_turns`, and
`delete_all_memories` are all already implemented from step 2. **This step writes no new database code.**
It is close to pure plumbing: get a real Telegram update into `run_turn`, get the result back out, handle
commands and failures around the edges.

No new design decisions should be needed here if the earlier phases were followed; where one surfaces
anyway, treat that as a sign something in the design docs was underspecified, not as license to improvise
silently — flag it instead.

---

## Files to write

All new, under `remember_this/bot/` (currently empty except `__init__.py`) and one small addition to
`remember_this/config.py`.

| File | Purpose |
|---|---|
| `remember_this/bot/telegram_client.py` | Thin wrapper over the Telegram Bot API: `send_message`, `answer_callback_query`, `edit_message_text` (or similar) via `httpx`. No FastAPI, no business logic — just HTTP calls out to Telegram. |
| `remember_this/bot/keyboards.py` | Builds the inline keyboard payload for `/forget`'s confirmation, and the `callback_data` encoding/decoding used to interpret a button tap. |
| `remember_this/bot/commands.py` | Handlers for `/start`, `/help`, `/forget` (both the initial command and its callback). No LLM calls. |
| `remember_this/bot/handlers.py` | The actual routing logic: given a parsed update, decide command vs. plain text vs. callback, call the right handler, call `run_turn` for plain text, map exceptions to the failure-table text. This is the file that ties everything together. |
| `remember_this/bot/webhook.py` | The FastAPI app and the single `/webhook/{...}` route. Thin — parses the raw JSON, does the idempotency check, delegates to `handlers.py`. |
| `remember_this/bot/scripts/register_webhook.py` (or alongside `scripts/` at repo root, your call) | One-off script that calls Telegram's `setWebhook`. Not part of the running service. |
| `remember_this/config.py` (edit, not new) | Add a `telegram_webhook_secret: SecretStr` field — see Part 0. |
| `.env.example` (edit) | Add `TELEGRAM_WEBHOOK_SECRET=placeholder` to match. |

Keep `telegram_client.py` free of any reference to `run_turn`, the database, or Langfuse — it should be
usable in isolation, the same way `remember_this/retrieval/embeddings.py` is just "talk to the embeddings
API" with nothing else mixed in. `handlers.py` is where everything else meets.

---

## Part 0 — Concepts you need first

### Webhook vs. the Bot API

Telegram's Bot API is just HTTPS. A webhook means you register a URL with Telegram once
(`setWebhook`), and Telegram POSTs every update to that URL. You do not poll — this was decided in ADR-006
specifically because polling needs an always-on process, which is incompatible with Cloud Run scaling to
zero. Two separate directions of traffic:

- **Receiving**: your service exposes an HTTPS endpoint (`webhook.py`); Telegram calls it.
- **Sending**: your service calls Telegram's API (`https://api.telegram.org/bot<token>/sendMessage`,
  `.../answerCallbackQuery`, etc.) to reply. Ordinary outbound HTTP — `httpx` is already a dependency, no
  new library needed for this half.

### Library or raw `httpx`?

Decide this before writing `telegram_client.py`. A Telegram client library (`python-telegram-bot`,
`aiogram`) gives you typed update objects and webhook-registration helpers. Raw `httpx` against the Bot
API's plain JSON/HTTP interface keeps one less framework's internals between you and the trace — consistent
with how this project has avoided frameworks everywhere a thin direct call would do (e.g. `openai`/`httpx`
over a heavier SDK elsewhere in the codebase). Given the actual surface needed here is small (receive one
POST shape, send a message, send/edit an inline keyboard, acknowledge a callback), raw `httpx` is the
better fit for this project's own stated preference for legibility, but it is a real choice — look at
Telegram's Bot API docs (https://core.telegram.org/bots/api) for the exact request/response shapes for
`sendMessage`, `answerCallbackQuery`, and `setWebhook` before committing either way.

### What an update actually looks like

A plain text message:

```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 42,
    "from": {"id": 987654321, "first_name": "..."},
    "chat": {"id": 987654321, "type": "private"},
    "text": "my student id is ABCDEF",
    "date": 1234567890
  }
}
```

A callback query (inline keyboard button tap) looks different — top-level key is `callback_query`, not
`message`:

```json
{
  "update_id": 123456790,
  "callback_query": {
    "id": "4382bfdwdsb323b2d9",
    "from": {"id": 987654321, "first_name": "..."},
    "message": {"message_id": 43, "chat": {"id": 987654321}},
    "data": "forget:confirm:987654321"
  }
}
```

`webhook.py` branches on which top-level key is present. Note `chat.id` and `from.id` are the same number
for a private DM (which is all this bot supports, per the product contract) — but don't conflate them
carelessly in code; `from.id` is "who sent this" and is the one that matters for isolation and for
verifying a callback (see Part 3).

### FastAPI as the webhook host

`fastapi` and `uvicorn` are already dependencies (check `pyproject.toml` — confirmed present). One route:

```python
# remember_this/bot/webhook.py
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/{secret_path_token}")
async def webhook(secret_path_token: str, request: Request) -> dict:
    ...
    return {}
```

Two decisions, not deferrable:

- **Authenticate the request.** Telegram supports a `secret_token` set at `setWebhook` time, which it then
  echoes back on every request as the `X-Telegram-Bot-Api-Secret-Token` header — check this header against
  `settings.telegram_webhook_secret` before processing anything. Without it, anyone who finds your URL can
  POST fabricated updates. This is the real reason for the new config field above. (A secret path segment,
  as sketched above, is a reasonable *addition* but not a substitute — headers aren't logged by proxies the
  way URLs sometimes are.)
- **Return the response only after the whole turn is done.** Per ADR-006, the entire turn — extraction,
  retrieval, answering — runs inside this request handler. Returning early would mean Telegram considers
  the update delivered while your own processing might still be running or might fail silently afterward.

---

## Part 1 — Idempotency

Already built: `remember_this/db/repository.py`'s `claim_update(update_id: int) -> bool` (confirmed present
from step 2 — read it before writing anything here, don't re-derive the signature). Call it first, before
anything else, inside `webhook.py` or at the very top of `handlers.py`:

```python
if not await db.claim_update(update["update_id"]):
    return {}  # already processed -- Telegram is retrying, 200 with no further action
```

This is not optional polish — a duplicate update that re-runs extraction would store the same fact twice
(ADR-006). If this check were missing, this step would need to build it; it is not missing, so this step's
job is only to call it in the right place, every time, before any other branch.

---

## Part 2 — Routing an update

`handlers.py`'s core job. Four shapes, matching `phase-1-interaction-model.md`'s taxonomy plus Telegram's
own message/callback split:

1. **A command** — Telegram sends `/start`, `/help`, `/forget` as ordinary messages whose `text` starts
   with `/`. Dispatch to `commands.py` before anything touches `run_turn` — these are deterministic, no
   LLM, no rate limit (see Part 4).
2. **A plain text message** — call `run_turn(user_id, text)` (from `remember_this/agent/runner.py`) and
   relay `TurnResult.reply` back via `telegram_client.send_message`. Do not add any wording of your own
   here — `TurnResult.reply` is already the complete, final user-facing text. Adding a greeting or sign-off
   in `handlers.py` would make this file a second place that composes user-facing text, which is exactly
   what ADR-005/step 6 avoided by keeping the top-level agent a relay rather than a second author.
3. **A callback query** — only `/forget`'s confirmation uses this right now (see Part 3). Route by parsing
   `callback_data` via whatever encoding `keyboards.py` defines.
4. **Anything else** (photos, stickers, voice, forwarded messages — anything without a `text` field on a
   `message`, and not a `callback_query`) — out of scope per the product contract (text only,
   `docs/design/phase-0-product-contract.md`). Decide: silently ignore, or reply "I only understand text
   messages." Either is fine; pick one, document the choice in a comment, and make sure the branch is
   actually reachable rather than falling through to an exception.

---

## Part 3 — Commands

`commands.py`. All deterministic, no LLM, no `run_turn` calls.

### `/start`

Static greeting plus a one-line description of what the bot does. No database call.

### `/help`

Static text. This is also where the privacy disclosure required by ADR-007 and
`phase-6-observability.md`/`phase-8-safety-and-failure.md` has to live — state plainly, in the actual
`/help` text:

- messages and answers are traced to a third-party observability tool (Langfuse) for roughly a month
- `/forget` deletes stored memories but does **not** purge those traces
- the bot is open to anyone who finds it, not restricted to any particular group (ADR-009) — so don't
  imply family-only privacy

This isn't boilerplate — it's the thing that makes ADR-007's privacy posture (disclosure over technical
enforcement) actually true rather than only documented. Write the exact wording here, in this file, not as
a placeholder to fill in later.

### `/forget`

Per `phase-1-interaction-model.md`: deletes **all** of the calling user's memories, after an explicit
confirmation step. First real use of the inline-keyboard mechanism.

Flow:
1. `/forget` received → `commands.py` builds a confirmation message with an inline keyboard from
   `keyboards.py` (two buttons: confirm / cancel), sent via `telegram_client.send_message`.
2. User taps a button → Telegram sends a `callback_query` update → `handlers.py` routes it to
   `commands.py`'s callback handler.
3. **Verify the callback's `from.id` matches whatever user id the `callback_data` claims to act on, before
   doing anything.** Do not trust `callback_data` alone — see Part 3's security note below.
4. On confirm: call `db.delete_all_memories(user_id)` (already exists, step 2), then
   `telegram_client.answer_callback_query` (see below) and edit or send a confirmation message.
5. On cancel: just acknowledge, no database call.

**`callback_data` must not be trusted as the sole source of truth for whose data gets deleted.** Encode the
user id into it if useful for your own bookkeeping, but always re-check it against
`callback_query["from"]["id"]` — the actual sender — before acting. This matters because `callback_data` is
visible to the Telegram client and, depending on how it's constructed, is not necessarily tamper-proof in
a way you should rely on. Treat the callback's own `from.id` as the authoritative identity, same as a plain
message's `from.id`.

**Every callback query must be acknowledged via `answerCallbackQuery`**, independent of any message you
send back. Look this up in the Bot API docs — skipping it leaves the tapped button showing a loading
spinner on the user's client indefinitely, with no error on your side to tell you something's wrong.

---

## Part 4 — Rate limiting

Already built: `record_turn(user_id)` and `count_recent_turns(user_id, since) -> int` in `repository.py`
(step 2). This step's job is only to call them at the right point in `handlers.py`:

```python
since = datetime.now(timezone.utc) - timedelta(hours=1)
if await db.count_recent_turns(user_id, since) >= settings.rate_limit_per_user_per_hour:
    await telegram_client.send_message(chat_id, "You've hit the hourly limit, try again shortly.")
    return
await db.record_turn(user_id)
```

Decide, deliberately, where this sits relative to command handling: `/start`, `/help`, `/forget` are cheap
and don't touch the LLM, so they should probably bypass the rate limit entirely. Apply the check only on
the branch that leads to `run_turn`. Don't apply it uniformly by accident — that would rate-limit
`/forget`, which is a real usability problem for no benefit (ADR-009's whole point for rate limiting is
bounding LLM/quota consumption, which `/forget` doesn't touch).

---

## Part 5 — Failure behaviour

The table in `docs/design/phase-8-safety-and-failure.md` is the literal spec for this part — implement the
rows as written, do not invent new wording or new categories. Re-read it now if you haven't recently;
summarizing it here would risk drift between the design doc and what gets built.

Structural points that apply regardless of the exact wording:

- **Fail fast, no retries**, inside the webhook handler. The one retry budget that exists already lives
  inside `retrieve()`'s relaxed-threshold pass (step 4) — retrying the *whole turn* again here would fight
  Telegram's own patience and risk a duplicate delivery that idempotency then has to absorb (ADR-006).
- **Every handled failure still returns 200 with a clear in-chat message.** An *unhandled* exception that
  escapes the FastAPI route and produces a 500 is the thing to avoid — it triggers a Telegram retry (which
  idempotency absorbs, so no double-processing, but it's a worse experience than an immediate clear
  message). Wrap the `run_turn` call and the command handlers in a try/except in `handlers.py` that maps
  exception types to the failure table's text.
- **Distinguish failure types in the trace, not only in the user-facing text.** An LLM-down failure and a
  database-down failure can show similar wording to the user but should be identifiable apart in Langfuse —
  this is largely free if you let each failure branch's exception type/message simply propagate into
  whatever span is active when it's caught, rather than catching broadly and discarding the detail.

---

## Part 6 — Registering the webhook

A one-time (or one-per-deploy) action, not application code:

```
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_URL>/webhook/<path-token>&secret_token=<SECRET>"
```

Write this as a small standalone script rather than running it from `webhook.py`'s startup — registering
on every process start is unnecessary (Telegram remembers the registration) and makes local development,
where your URL changes constantly, more annoying rather than less.

For local development: per `phase-5-infrastructure.md`'s own note on this, you have two options and don't
need to pick only one — (a) tunnel your local server and temporarily re-point the single webhook, accepting
production goes quiet meanwhile, or (b) test the webhook route directly with a hand-constructed JSON
payload (the shapes in Part 0) posted straight at your local FastAPI instance, which needs no tunnel and no
real Telegram interaction. Prefer (b) for most of this step's verification; reserve (a) for a final
end-to-end check with a real Telegram client.

---

## Pitfalls

- Returning a response before the turn finishes defeats the "process fully inside the request" design from
  ADR-006.
- Trusting `callback_data` without checking it against the callback's actual sender (`from.id`) is a real
  security gap, not a theoretical one.
- Forgetting `answerCallbackQuery` leaves the user's button in a spinning state with no error to tell you.
- An unhandled exception producing a 500 triggers a Telegram retry — every failure-table row needs to be
  actually reachable in a test, not just described in a comment.
- Don't let `handlers.py` compose any new user-facing wording beyond what `run_turn` and the static command
  text already provide.
- Don't apply the rate limit to `/start`/`/help`/`/forget` — only to the branch that calls `run_turn`.
- `claim_update`, `record_turn`, `count_recent_turns`, `delete_all_memories` already exist — if you find
  yourself about to write a new database function for any of these, stop and re-check `repository.py` first.

## Done when

- A hand-constructed update payload for a plain text message, posted directly at the local FastAPI route,
  produces a correct `run_turn` call and a well-formed reply.
- The same `update_id` posted twice only processes once (second call returns `{}` immediately, no second
  `run_turn` call, confirmed by log/trace).
- `/start` and `/help` return static text with no LLM or database call involved.
- `/forget` round-trips through a real inline keyboard and callback against a live Telegram chat, deletes
  only the confirming user's memories, and the button is acknowledged (no stuck spinner).
- A rate-limited user sees the ADR-009 message, and `/start`/`/help`/`/forget` are confirmed to bypass the
  limit.
- Every row in `phase-8-safety-and-failure.md`'s failure table has been exercised at least once (simulate
  it — e.g. temporarily point `DATABASE_URL` at something invalid — rather than waiting for it to happen
  naturally) and produces its specified text without a 500.
- The webhook request is confirmed to reject a request missing or mismatching the Telegram secret token.
- You can state, in one sentence, why `callback_data` alone is not sufficient to identify who a `/forget`
  confirmation applies to.
