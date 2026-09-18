# Step 1 — Repo skeleton, dependencies, configuration

Directories and `__init__.py` files are created. Everything else in this step is yours to write.

## Layout and responsibilities

```
remember_this/
  config.py            settings loaded from environment, validated once at import
  errors.py            the project's own exception types
  db/
    schema.sql         tables and the pgvector index
    repository.py      all data access; every function takes a user id
  llm/
    client.py          OpenAI-compatible client wiring, model identity from config
    extraction.py      message -> atomic facts (structured output)
    relevance.py       weak candidates -> can this question be answered
    answer.py          facts + question -> answer, citation, abstention flag
    prompts/           prompt text, versioned in git (ADR-010)
  retrieval/
    embeddings.py      text -> vector
    search.py          vector search, strict/relaxed thresholds, the retry decision
  agent/
    agent.py           the Pydantic AI agent
    tools.py           save_memories, search_memories, request_clarification
  bot/
    webhook.py         FastAPI app and the webhook endpoint
    handlers.py        message and callback routing, commands
    keyboards.py       inline keyboards for clarification, /forget, feedback
  observability/
    tracing.py         OTel/Langfuse setup, span helpers, user id hashing
evals/
  generate/            dataset generation scripts
  harness/             run definitions and metric implementations
  data/                generated dataset files under review
tests/
```

Note on naming: the bot package is `bot/`, not `telegram/`, because `telegram` is the import name of a
popular Telegram library and a local package with that name would shadow it.

## Why this shape

Each subpackage matches a phase decision, so a design change lands in one place. `llm/` holds the four
LLM steps from ADR-005 as separate modules because each is independently evaluated in Phase 7 — if they
were one file the eval suites would have nothing clean to target. `evals/` sits outside the application
package because it is tooling, not runtime.

## What to write

### 1. `pyproject.toml` — via uv

Package manager: **uv**. Sequence:

1. Install uv if absent: `brew install uv`. Verify with `uv --version`.
2. `uv init --bare` in the repo root — creates `pyproject.toml` and nothing else. (If your uv predates
   `--bare`, use `uv init --package` and delete the sample module and `main.py` it generates.)
3. `uv python pin 3.12` — writes `.python-version` so every machine and the Dockerfile agree.
4. Edit `pyproject.toml`: set `name`, `description`, `requires-python`.
5. Add runtime dependencies with `uv add <pkg>` (see the list below). uv writes them to `pyproject.toml`,
   resolves, and creates `.venv` and `uv.lock`.
6. Add tooling to a dev group so it stays out of the production image:
   `uv add --dev pytest ruff`.
7. Commit `pyproject.toml`, `uv.lock`, and `.python-version`. The lockfile is the point of using uv —
   without it committed, builds are not reproducible.

Day-to-day afterwards: `uv sync` to match the lockfile, `uv run <cmd>` to run inside the environment
without activating it, `uv add`/`uv remove` to change dependencies. Never `pip install` into `.venv`; it
desynchronises the lockfile.

For the Dockerfile in step 10: `uv sync --frozen --no-dev` installs exactly the lockfile and skips dev
tooling.

Python version: 3.12 is a safe choice.

Dependencies you will need, roughly in the order the build touches them:

- `pydantic-settings` — config loading and validation
- `pydantic-ai` — the agent (ADR-005)
- `openai` — the OpenAI-compatible client for university endpoints (C1)
- `psycopg` (v3) or `asyncpg` — Postgres driver. Your choice, but pick one and be consistent about
  async: the webhook path is async, so an async driver avoids blocking the event loop.
- `pgvector` — the Python helper for vector types
- `fastapi` and `uvicorn` — webhook host
- `httpx` — Telegram Bot API calls
- `langfuse` and/or the OpenTelemetry SDK — decide in step 7, but note it now

Pin versions. Do not add a Telegram bot framework yet — that decision is still open and you may end up
calling the Bot API directly with `httpx`.

### 2. `.env.example`

Every variable the app reads, with placeholder values, committed. The real `.env` is gitignored.

From the design docs, the configuration surface is:

- `TELEGRAM_BOT_TOKEN`
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`
- `JUDGE_MODEL`, `GENERATOR_MODEL` (ADR-008 requires these differ from `LLM_MODEL`)
- `DATABASE_URL`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- `STRICT_THRESHOLD`, `RELAXED_THRESHOLD`
- `PROMPT_VERSION`
- `RATE_LIMIT_PER_USER` and its window
- `USER_ID_SALT` — for hashing Telegram ids before they reach Langfuse (ADR-007)

### 3. `remember_this/config.py`

A single settings object, loaded and validated once. Decisions to make:

- Which values have defaults and which must be present. Missing secrets should fail at startup, not at
  first use — a Cloud Run instance that boots and then fails on the first message is harder to debug.
- Whether thresholds live here or in a separate tuning config. They are swept during evals (ADR-004), so
  they need to be overridable per run without editing code.

Requirement from ADR-006 and ADR-007: thresholds, model identity, and prompt version must be readable at
runtime so they can be attached to every trace. Design for that now rather than retrofitting.

### 4. `.gitignore`

`.env`, `__pycache__`, virtualenv directory, any generated eval output you do not intend to commit.

### 5. `remember_this/errors.py`

Optional now, but worth a thought. Phase 8 defines distinct user-visible failures — LLM unavailable,
database unavailable, invalid extraction, rate limited. Distinct exception types make the handler a
readable mapping rather than a pile of string checks.

## Pitfalls

- **`USER_ID_SALT` must be stable.** If it changes, old traces stop correlating with new ones. It is
  config, not something regenerated per deploy.
- **Do not let config read the environment at call time.** Load once; otherwise tests and eval runs
  become order-dependent.
- **Judge and generator models must differ from the system model** (ADR-008). If your university endpoint
  exposes only one model, that is a real constraint worth discovering now rather than in step 8 — check
  what is actually available before you finish this step.
- **Async consistency.** Choosing a sync Postgres driver now means either blocking the event loop later or
  a rewrite. Decide deliberately.

## Done when

- `pip install -e .` (or `uv sync`) succeeds in a clean virtualenv.
- `python -c "from remember_this.config import settings; print(settings)"` prints your config with values
  drawn from `.env`, and fails loudly when a required variable is missing.
- `.env.example` lists every variable; `.env` is ignored by git.
- You can state which models your university endpoint exposes, and which you will use for system, judge,
  and generator roles.
