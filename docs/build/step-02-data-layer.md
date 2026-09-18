# Step 2 — Data layer

Files you will write: `remember_this/db/schema.sql`, `remember_this/db/repository.py`, and a small script to
apply the schema.

Design references: `phase-2-memory-representation.md` and ADR-003 (what a memory is), ADR-006 (idempotency),
ADR-009 (isolation, rate limiting).

---

## Part 0 — Concepts you need first

### What pgvector is

Postgres has no native type for embeddings. `pgvector` is an extension that adds:

- a `vector(N)` column type holding N floats
- distance operators between vectors
- index types that make nearest-neighbour search fast

It has to be enabled once per database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

On Neon this is available on the free plan; you just run the statement.

### Distance vs similarity

pgvector gives you **distance** operators. You want **similarity** for your thresholds. Three operators exist:

| Operator | Meaning |
|---|---|
| `<->` | Euclidean (L2) distance |
| `<=>` | Cosine distance |
| `<#>` | Negative inner product |

You want cosine, so `<=>`. The conversion is:

```
cosine_similarity = 1 - cosine_distance
```

So a memory whose embedding is at cosine distance 0.3 from the query has similarity 0.7. Your
`STRICT_THRESHOLD=0.65` means you accept rows where `1 - (embedding <=> $query) >= 0.65`.

Getting this backwards is the single most common pgvector bug: a threshold applied to distance instead of
similarity silently inverts your entire retrieval behaviour, returning the *least* relevant rows. Write it
once, carefully, and test it with two obviously-related and two obviously-unrelated sentences.

### Vector dimensions

`bge-m3` produces **1024-dimensional** vectors (C7). The column must be `vector(1024)`. If the number
disagrees with what the model returns, Postgres raises an error on insert — annoying but at least loud.

### Indexes

Two index types: `ivfflat` and `hnsw`. HNSW is the better default — higher recall, no training step, slower
to build. Syntax:

```sql
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
```

The `vector_cosine_ops` part must match the operator you query with (`<=>`). If you build a `vector_l2_ops`
index and query with `<=>`, the index is silently ignored and you get a sequential scan.

Honest note: at hundreds of rows Postgres will often choose a sequential scan anyway because it is cheaper
than the index. Build the index regardless — it is a study goal (ADR-004) — but do not be surprised when
`EXPLAIN` shows a seq scan. That is correct behaviour, not a bug.

---

## Part 1 — `schema.sql`

Design the tables yourself. Here is what the design docs require, and the decisions each one contains.

### `messages`

From ADR-003: the verbatim inbound text, never rewritten.

Needs: an id, the owning user, the raw text, and when it arrived.

Decisions for you:

- **Id type.** `bigserial` (auto-incrementing integer) or `uuid`. Integers are shorter, which matters because
  memory ids are cited in answers to the user (ADR-001). UUIDs avoid guessable ids. At five trusted users,
  either is defensible.
- **User id type.** Telegram user ids are 64-bit integers, so `bigint`. Do not use `int`.
- **Timestamps.** Always `timestamptz`, never `timestamp`. `timestamp` has no timezone and will silently
  misrepresent times once the server and your laptop disagree. Default it to `now()`.

### `memories`

One atomic extracted fact (ADR-003).

Needs: an id, the owning user, a reference to the source message, the fact text, the embedding, and a
creation timestamp.

Decisions for you:

- **Foreign key to `messages`,** with what delete behaviour? `ON DELETE CASCADE` means deleting a message
  removes its memories, which is what `/forget` wants. Without it you must delete in the right order
  yourself.
- **Is `user_id` duplicated here** when it could be reached through `message_id`? Denormalising it means
  every retrieval query filters on a column in the table it is already scanning, rather than joining. Given
  isolation is the highest-severity bug class (ADR-009), the redundancy buys simplicity where it matters.
  Your call, but decide deliberately.
- **`created_at` is required** even though it duplicates the message's timestamp — ADR-003 keeps it
  specifically so latest-value lookup stays addable later.
- **Should `embedding` be nullable?** If extraction and embedding happen in one transaction, no. If you ever
  want to backfill embeddings separately, yes.

### `processed_updates`

From ADR-006: Telegram retries updates, and a retry that re-runs extraction would store facts twice.

Needs: Telegram's `update_id` as the primary key, and when it was seen.

The mechanism: before processing, try to insert the `update_id`. If the insert violates the primary key, this
is a retry and you stop. This is more reliable than "select then insert", which has a race between the two
statements. Look up `INSERT ... ON CONFLICT DO NOTHING` and note that it tells you whether a row was
actually inserted.

Decision: do these rows live forever? A few hundred per year is nothing, so pruning is optional. Say what
you chose.

### Usage tracking and rate limiting

From ADR-009: a per-user hourly cap, and a dashboard view of who is using the bot.

Note the subtlety — you cannot count rows in `messages` to rate limit, because questions are not stored as
messages. Only feed messages produce message rows. So you need something that records **every turn**.

Two shapes:

- **An event log**: one row per turn with a user id and timestamp. Rate limiting is a `COUNT(*)` over the last
  hour. Also answers the dashboard question. Grows unboundedly but slowly.
- **A counter with a window**: one row per user holding a count and a window start, reset when the window
  expires. Smaller, but loses history, so the dashboard gets nothing.

There is also a `users` table worth considering: Telegram id, first seen, last seen. ADR-009 noted that
Langfuse only holds *hashed* ids, so if you ever need to block someone, the real id has to be in your
database. That table is where it lives.

### Indexes to create

- the HNSW index on `memories.embedding`
- an index on `memories.user_id` — every query filters on it
- an index on whatever your usage log filters by (user id and timestamp)

---

## Part 2 — Neon setup and applying the schema

### Migration strategy

You have no migration tool. Two options:

- **`schema.sql` plus a small script** that connects and executes it, safe to run repeatedly
  (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`). Simple, honest, fine for a project that will
  not evolve much.
- **Alembic.** Proper versioned migrations. Correct for a long-lived project, more machinery than four
  weekends wants.

Recommendation: the script, and note in the README that migrations are deliberately out of scope.

### Creating the Neon project

1. Sign up at [neon.com](https://neon.com) — GitHub sign-in is fine. No credit card needed for the Free plan.
2. Create a project. Name it `remember-this`.
3. **Choose the region deliberately.** Pick the region you will run Cloud Run in. Database and application in
   different continents adds a round trip to every query, and you make several per turn. If unsure, pick the
   region closest to you and note it — you will match Cloud Run to it in step 10.
4. Accept the default Postgres version and the default database name (`neondb`).
5. The dashboard shows a **connection string**. Copy it.

### Direct vs pooled endpoint — read this before copying the string

Neon exposes two hostnames for the same database:

- **Pooled**: hostname contains `-pooler`. Routes through a connection pooler.
- **Direct** (sometimes labelled unpooled): no `-pooler` in the hostname.

The dashboard usually offers the pooled one by default, and there is a toggle to reveal the direct one.

This matters because of the asyncpg gotcha below: the pooler runs in transaction mode, which breaks asyncpg's
prepared statements unless you disable its statement cache. You are running one small service with its own
pool, so you do not need Neon's pooler at all.

**Use the direct endpoint.** If you later switch to the pooled one, set `statement_cache_size=0` on the
asyncpg pool.

### Fixing up the connection string for asyncpg

Neon's string looks roughly like:

```
postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

asyncpg understands `sslmode`. It does **not** understand `channel_binding`, and will raise an error about an
unexpected parameter rather than ignoring it. Remove that parameter before putting the string in `.env`:

```
DATABASE_URL=postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

Keep `sslmode=require`. Neon rejects unencrypted connections.

Two more notes:

- If your password contains characters like `@`, `/`, or `#`, they must be percent-encoded in the URL, or the
  parser will misread where the host begins.
- Neon Free suspends compute after about five minutes idle. Your first query after a pause takes noticeably
  longer while it wakes. That is expected (ADR-006) and is exactly the cold-start latency you will measure
  later.

### Running the schema

Three routes. Do the third, but the first is a useful sanity check.

**Route A — Neon SQL Editor (fastest, no local setup).** Open your project in the Neon console, go to the SQL
Editor, paste the contents of `schema.sql`, run it. Good for a first pass and for poking at data later.

**Route B — `psql`.** On macOS, `psql` is not installed by default. `brew install libpq` gives it to you, but
libpq is keg-only so it does not land on your `PATH` automatically — brew prints the `export PATH=...` line to
add. Then:

```
psql "$DATABASE_URL" -f remember_this/db/schema.sql
```

**Route C — a Python script in the repo.** This is the one to keep, because it means "set up the database" is
a command anyone can run, including future you on a new machine.

Write `scripts/init_db.py`. What it needs to do:

1. Read `DATABASE_URL` from your settings — reuse `get_settings()` rather than reading the environment again.
2. Read `schema.sql` from disk. Locate it relative to the file rather than the current working directory, or
   the script only works when run from the repo root. `pathlib.Path(__file__).parent` is the usual approach.
3. Connect with `asyncpg.connect(...)`, execute the SQL, close.

The useful detail: **asyncpg's `connection.execute()` will run multiple statements in one call**, but only
when you pass no query arguments. Since your schema has no parameters, you can hand it the whole file as one
string. If you were passing arguments you would have to split the statements yourself.

Because it is an async function you need `asyncio.run(...)` at the entry point.

**Run it as a module, not as a file path.** From the repo root:

```
uv run python -m remember_this.db.scripts.init_db
```

Why the distinction matters: when Python runs a *file*, it puts that file's own directory on `sys.path`, so
`from remember_this.config import ...` fails with `ModuleNotFoundError`. When you run `-m` from the repo root,
the current directory goes on `sys.path` instead and the package resolves. This applies to every script in
this project, so get used to the `-m` form now.

(The alternative is adding a build backend to `pyproject.toml` and installing the project as an editable
package, which makes imports work from anywhere. Not necessary yet.)

Note also that `get_settings()` reads `.env` relative to the **current working directory**, so scripts must be
run from the repo root regardless.

### Verifying it worked

Run these in the SQL Editor, or add them as prints at the end of your script:

```sql
-- extension present?
SELECT extname FROM pg_extension WHERE extname = 'vector';

-- tables created?
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- indexes on memories, including the HNSW one?
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'memories';
```

Then run the script a second time. It must succeed with no error — that is what proves the `IF NOT EXISTS`
clauses are doing their job, and it is the property that makes the script safe to run on every deploy if you
ever want that.

---

## Part 3 — `repository.py`

This module owns every SQL statement in the project. Nothing else in the codebase should contain SQL.

### Connection pooling

Opening a connection per query is slow — worse here, because Neon may need to wake. asyncpg provides a pool:
you create it once at startup and acquire connections from it per query.

Two things to get right:

**Registering the vector type.** asyncpg does not know what a `vector` is; without registration you get
strings back instead of vectors, and inserts fail. The `pgvector` package provides a registration function
for asyncpg connections. It must run on **every** connection in the pool, which is what the pool's `init`
callback parameter is for. Look up `pgvector.asyncpg.register_vector` and `asyncpg.create_pool(init=...)`.

**Where the pool lives.** A module-level global created lazily is simplest. A pool created in FastAPI's
`lifespan` and stored on app state is cleaner and shuts down properly. You will need the pool from eval
scripts too, not just the web app, so whatever you choose must work outside FastAPI.

### asyncpg gotchas that will cost you an hour each

- **`statement_cache_size=0` is required if you use Neon's pooled endpoint.** Poolers in transaction mode
  break asyncpg's prepared statements, and the error message will not tell you that. Either use the direct
  endpoint or disable the statement cache.
- **asyncpg rejects unknown query parameters in the DSN.** Neon connection strings sometimes carry
  `channel_binding=require` or similar, which asyncpg does not understand. Strip parameters it does not
  accept, or pass SSL settings as arguments instead of in the URL.
- **asyncpg uses `$1, $2` placeholders**, not `%s`. It has no string-formatting path at all, which is good:
  parameterised queries are the only option, so SQL injection is not reachable here.

### Functions to write

Signatures are yours to design, but these operations are needed. Note that **every one takes a user id** —
required positional, never optional. ADR-009 calls a forgotten filter the highest-severity bug available in
this system, and a required argument is the cheapest structural defence against it.

| Operation | Notes |
|---|---|
| record/refresh a user | called on every turn; upsert on Telegram id |
| save a message | returns the new message id |
| save memories | takes facts *with* their embeddings; see transaction note below |
| search memories | takes a query embedding and a similarity threshold; returns rows with their similarity |
| delete all memories for a user | `/forget` |
| claim an update id | returns whether this is a fresh update or a retry |
| record a turn / count recent turns | rate limiting |

### The transaction that matters

Saving a message and its extracted memories must be **atomic**. If the message row is written and the memory
rows are not, you have a stored message the user was told about with nothing retrievable behind it. Wrap both
in one transaction: `async with conn.transaction():`.

Inserting several memories at once: `executemany` works. Read up on it and decide whether one statement per
fact is acceptable at your volume (it is).

### The search query

The shape is:

```sql
SELECT id, fact_text, created_at,
       1 - (embedding <=> $2) AS similarity
FROM memories
WHERE user_id = $1
  AND 1 - (embedding <=> $2) >= $3
ORDER BY embedding <=> $2
LIMIT $4
```

Points to understand rather than copy:

- `1 - (embedding <=> $2)` appears twice: once to return, once to filter. You can avoid the repetition with a
  subquery or CTE if you prefer.
- `ORDER BY embedding <=> $2` — ascending distance is descending similarity. Ordering by `similarity DESC`
  works too but only the distance form can use the HNSW index.
- The `LIMIT` is the "generous hard cap" from ADR-004, not the selector. The threshold selects; the limit
  only stops a pathological case.
- `WHERE user_id = $1` is the isolation boundary. Everything else in this project is recoverable; this line
  is not.

### Returning results

Decide what `search_memories` returns. Raw asyncpg `Record` objects leak the driver into the rest of the
codebase. A small Pydantic model or dataclass per row keeps the boundary clean and gives the retrieval and
answer steps something typed to work with. You already have Pydantic as a dependency.

---

## Pitfalls summary

- Similarity vs distance inversion — test it deliberately.
- Index ops class must match the query operator, or the index is silently unused.
- `timestamptz`, never `timestamp`.
- Vector registration must happen on every pooled connection.
- Neon pooled endpoint plus asyncpg needs `statement_cache_size=0`.
- Message and memories must be written in one transaction.
- Every function takes a user id.

---

## Done when

- `CREATE EXTENSION vector` has run on your Neon database.
- Your schema script runs twice in a row without error (proving it is idempotent).
- A throwaway script can: insert a message, insert two memories with hand-made 1024-dim vectors, search with
  one of those vectors, and get back the matching row with a similarity near 1.0.
- Searching as a *different* user id returns nothing. Write this check explicitly — it is the isolation
  guarantee, and it becomes an eval case later (ADR-009).
- Claiming the same `update_id` twice reports fresh the first time and duplicate the second.
- `EXPLAIN` on your search query runs without error. Whether it uses the index or a seq scan is not the point.
