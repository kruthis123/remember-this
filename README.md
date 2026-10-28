# Remember This

A small memory assistant that stores facts expressed in plain English and answers questions about them later —
for example, "the Wi-Fi password at the cabin is ...", followed weeks later by "what is the Wi-Fi password
at the cabin?". Runs as a Telegram bot.

The main purpose of the project is to learn **LLM observability and evaluation**: tracing an LLM-driven
system, building a dataset to measure it against, using LLM judges where deterministic checks are not enough,
validating those judges against human labels, and using the results to guide changes.

## What it does

- Store a fact in natural language; an LLM extracts and confirms what it understood.
- Ask a question in natural language; it answers from what you've told it, citing the memory and date it
  came from — or says plainly that it has nothing on that topic.
- Point lookup only for now (one memory answers one question). No memory correction beyond wiping everything,
  no reminders, no group chats.

## Current implementation

The core agent is implemented in Python with [Pydantic AI](https://ai.pydantic.dev/). It uses Postgres with
`pgvector` for storage and retrieval and [Langfuse](https://langfuse.com/) for tracing. The bot runs on AWS Lambda behind a Lambda
Function URL, deployed via GitHub Actions on a tagged release.

## Eval results

Latest run against the 61-case hand-built eval set, at the thresholds chosen from the sweep:

| Metric | Result |
|---|---|
| Faithfulness (no fabricated detail) | 100% (61/61) |
| Correctness | 88.5% (54/61) |
| Verbatim fidelity (identifiers, proper nouns) | 95.8% (23/24) |
| Abstention correctness | 94.0% (47/50) |
| Attribution (cited memory supports the answer) | 100% (47/47) |
| Routing (correct tool chosen) | 100% (61/61) |


## AI Use Declaration

I deliberately built this project with very little AI-generated code. I made the product, architecture,
prompt, and evaluation decisions and wrote most of the implementation myself. I used AI as a learning and
review assistant: to explain unfamiliar concepts, challenge design choices, review code, suggest debugging
directions, and occasionally help with small, bounded pieces of code.

Through this project I learned how to define measurable LLM behavior, create and label evaluation data,
trace failures across an agent workflow, design LLM-as-judge checks, compare them with human judgments, and
use evaluation evidence rather than intuition to decide whether a change is an improvement.

## Documentation

- `docs/design/` — the full system design, phase by phase, with decision records (ADRs) explaining *why* each
  choice was made and what would trigger revisiting it.
- `PLAN.md` — implementation progress, step by step.
- `docs/build/` — a detailed how-to for each build step, written as the step is reached.

## Status

Built end to end and deployed. Ongoing work is refinement: tuning prompts and thresholds against the eval
harness as real usage surfaces new cases.
