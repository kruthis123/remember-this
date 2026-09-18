# Build plan

Status index for implementation. Design is finished and lives in `docs/design/` (start at
`docs/design/README.md`); this file tracks *building* it.

Each step below has a detailed write-up in `docs/build/step-NN-*.md`, written once you reach that step —
they are teaching documents assuming no prior familiarity with the libraries involved, not just checklists.

## Steps

| # | Step | Status | Doc |
|---|---|---|---|
| 1 | Repo skeleton, uv setup, dependencies, `config.py` | done | `docs/build/step-01-skeleton.md` |
| 2 | Data layer — Postgres schema, pgvector, `repository.py` | done | `docs/build/step-02-data-layer.md` |
| 3 | Extraction — raw message to atomic facts, structured LLM output | next | — |
| 4 | Retrieval — embeddings, vector search, strict/relaxed thresholds | not started | — |
| 5 | Answer generation — citation, abstention | not started | — |
| 6 | Agent wiring — Pydantic AI, the three tools, loop bounds | not started | — |
| 7 | Observability — Langfuse tracing across every step | not started | — |
| 8 | Eval dataset generation and harness | not started | — |
| 9 | Telegram bot — webhook, handlers, inline keyboards, idempotency | not started | — |
| 10 | Deploy — Dockerfile, GitHub Actions on tag, Cloud Run | not started | — |

Steps 1–8 produce a working, measured agent with no Telegram involved at all — deliberate, per ADR-001's
eval-before-bot commitment. Telegram is wired in at step 9, after the eval loop already exists.

## Time expectation

The original four-weekend estimate (ADR-001/`constraints.md`) was soft even at the time, and steps 1–2 alone
took several review cycles each with real bugs caught along the way. A more realistic expectation, writing the
code yourself with review at each step, is **6–8 focused sessions**, front-loaded on steps 3–6 (extraction,
retrieval, answering, agent wiring), which are both the most novel material and the ones with no established
pattern to lean on yet. Step 8's dataset generation is partly delegated, so it costs less of your time than its
scope suggests. Step 10 is short in code but often has real-world friction (cloud auth, first-deploy debugging)
that doesn't show up in a line count.

## Working agreement

See `.kiro/steering/collaboration.md`. Default is: the user writes the code, gets a detailed write-up per step,
and review after. Code is written for the user only when explicitly asked.
