# remember-this

A Telegram bot that remembers what you tell it in plain English and answers questions about it later —
"the wifi password at the cabin is ...", then weeks later, "what's the wifi password at the cabin?".

The bot is the excuse. The actual point of this project is hands-on practice with **LLM observability and
evaluation**: tracing every step of an LLM-driven system, building a dataset to measure it against, judging
its answers with other LLMs, validating those judges against human labels, and gating changes on the result —
the discipline that separates a demo from something you can trust.

## What it does

- Store a fact in natural language; an LLM extracts and confirms what it understood.
- Ask a question in natural language; it answers from what you've told it, citing the memory and date it
  came from — or says plainly that it has nothing on that topic.
- Point lookup only for now (one memory answers one question). No memory correction beyond wiping everything,
  no reminders, no group chats. See `docs/design/phase-0-product-contract.md` for the full scope and why.

## How it's built

Python, a [Pydantic AI](https://ai.pydantic.dev/) agent with three tools, Postgres with `pgvector` for storage
and retrieval, [Langfuse](https://langfuse.com/) for tracing, deployed on Google Cloud Run against a
[Neon](https://neon.tech/) database — all free-tier. LLM access is via university-hosted, OpenAI-SDK-compatible
endpoints.

## Documentation

- `docs/design/` — the full system design, phase by phase, with decision records (ADRs) explaining *why* each
  choice was made and what would trigger revisiting it. Start at `docs/design/README.md`.
- `PLAN.md` — implementation progress, step by step.
- `docs/build/` — a detailed how-to for each build step, written as the step is reached.

## Status

In progress. See `PLAN.md`.
