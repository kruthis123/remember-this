# Shortlists

Narrowed option sets for the two questions where surveying the whole field is a waste of your four
weekends. Each is presented with the axes that actually differentiate them. Choose in the relevant
phase and record an ADR. Free-tier details were current in September 2026 and are the sort of thing
that changes quietly — verify before committing.

---

## 1. Runtime and hosting (Phase 5)

Four separable decisions hide behind "which runtime". Decide them in this order, because each
constrains the next.

### 1a. Telegram transport: polling or webhook

| | Long polling | Webhook |
|---|---|---|
| Needs public HTTPS URL | no | yes |
| Needs always-on process | yes | no (can scale to zero) |
| Local development | trivial | needs a tunnel |
| Behaviour on restart | resumes, no updates lost | updates lost or retried depending on platform |
| Fits serverless | poorly | naturally |

This is the decision that determines your hosting options, not the reverse. Polling plus a
scale-to-zero host is a contradiction; webhook plus a scale-to-zero host means cold starts on the
first message after idle.

### 1b. Bot library

- **python-telegram-bot** — mature, async, its own job queue and handler abstractions. Opinionated;
  brings its own application lifecycle, which you will be tracing around.
- **aiogram** — async-first, lighter, router/middleware model that maps cleanly onto per-message
  tracing middleware.
- **Raw Bot API over httpx behind FastAPI** — most code, least magic, total control over the request
  path. Defensible if "I can explain every layer" is an explicit goal, wasteful otherwise.

Differentiating axis for this project: how easily you can wrap every inbound message in one trace
and attach a user id, and how much of the framework's internals end up in your spans.

### 1c. Compute host

| Option | Shape | Watch out for |
|---|---|---|
| Your own machine / Raspberry Pi / a university VM if you have one | always-on, polling-friendly, zero cost, full data control | uptime is your problem; not visible to a reviewer unless you document it |
| Google Cloud Run | scale-to-zero container, webhook-friendly, generous free request allowance | cold starts; needs a container; billing account required |
| Render free web service | simplest git-push deploy | free services sleep after ~15 minutes idle and cold-start on the next request ([overview](https://selfhost.hashnode.dev/best-render-alternatives-in-2026-ranked-compared)) — fine for a webhook, fatal for polling |
| Fly.io | small always-on VM, container-based, per-second billing | no meaningful free allowance any more; pure pay-as-you-go ([pricing comparison](https://dev.to/pavel-hostim/render-vs-railway-vs-flyio-pricing-compared-2026-2e5p)) — expect a couple of dollars a month |
| Hugging Face Spaces | free CPU tier, easy public URL | sleeps on inactivity; an unusual home for a bot, but genuinely free |
| Railway | good DX, usage-based | no free tier as of 2026 ([source](https://dev.to/pavel-hostim/render-vs-railway-vs-flyio-pricing-compared-2026-2e5p)) |

Note that Railway no longer offers a free tier and Fly.io removed its free allowances, so a lot of
"deploy your bot free" tutorials from 2023–2024 are now wrong. Content was rephrased for compliance
with licensing restrictions.

### 1d. Datastore

| Option | Vector support | Free-tier catch |
|---|---|---|
| Neon Postgres + pgvector | pgvector extension | compute suspends after ~5 min idle and wakes in well under a second; 0.5 GB per project on Free ([Neon free plan](https://neon.com/faqs/managed-postgres-databases-free-tier), [comparison](https://thedevopsdaily.hashnode.dev/neon-vs-supabase-free-tiers-we-benchmarked-both-so-you-don-t-have-to)) |
| Supabase Postgres + pgvector | pgvector extension | free projects pause after 7 days of inactivity and need manual restore ([details](https://dev.to/nayankyada/supabase-pricing-2026-free-tier-limits-compute-costs-when-to-upgrade-52af)) — a real risk for a low-traffic family bot |
| SQLite (+ sqlite-vec) on a persistent volume | extension or brute-force numpy | ties you to one always-on host with a disk; backups are manual |
| Dedicated vector DB (Qdrant/Chroma cloud free tiers) | native | a second datastore to operate alongside your relational data; ask whether the corpus justifies it |

At family scale the corpus is likely a few thousand short texts. Whether that needs a vector index
at all is a genuine Phase 3 question, and this table should not be read as implying it does.

---

## 2. Observability and evaluation platform (Phase 6, used in Phase 7)

Shortlist of three, all open-source-cored and self-hostable, all with usable free cloud tiers, all
with dataset + experiment + LLM-as-judge features (so one choice covers both phases). Ruled out for
this project: LangSmith (free tier capped around 5k traces/month and most natural if you commit to
LangChain/LangGraph), Braintrust and W&B Weave (good products, closed cores, less relevant to the
self-host/privacy angle in C6).

| | Langfuse | Arize Phoenix | Comet Opik |
|---|---|---|---|
| Core licence | MIT | open source | open source |
| Self-host | first-class, Docker Compose; full features, no usage caps on the MIT build ([self-hosting](https://langfuse.com/self-hosting), [teardown](https://getbeton.substack.com/blog/langfuse-pricing-teardown)) | first-class, no event caps when self-hosted ([comparison](https://www.morphllm.com/llm-observability-tools)) | first-class |
| Free cloud tier | Hobby: 50k units/month, ~30-day retention, 2 users ([pricing](https://langfuse.com/pricing), [breakdown](https://www.cekura.ai/blogs/langfuse-pricing)) | free tier plus a hosted commercial tier | free tier plus hosted commercial tier |
| Particular strength | prompt management + tracing + evals in one, widely adopted, strong OTel story | OpenTelemetry-native instrumentation and notably strong RAG/retrieval evaluation ([review](https://dupple.com/learn/best-llm-observability-tools)) | tight testing/CI workflow orientation |
| Consideration | units metric counts traces + observations + scores, so verbose tracing consumes the allowance faster | product line spans OSS Phoenix and commercial AX; know which you are learning | smaller community than the other two |

Content was rephrased for compliance with licensing restrictions.

### How to actually decide

Do not decide from this table. Pick the two that appeal, spend an hour each sending a handful of
hand-made traces through them, and judge on:

1. **Does its trace UI answer "why was this answer wrong" quickly?** That is the whole point.
2. **Prompt/dataset/experiment features** — will you be running evals inside this tool, or in your
   own harness with the platform only receiving results? Both are valid; they lead to different
   choices.
3. **Instrumentation coupling** — how much of your code has to know about this vendor. An
   OpenTelemetry-based path keeps the exit cheap; a vendor SDK is usually faster to get running.
4. **Where the data lives**, against your C6 posture. Self-hosting removes the question entirely at
   the cost of running one more container.
5. **Also relevant:** Langfuse offers grants for research and education use ([details](https://langfuse.com/research)),
   which may apply given your university context.

Write the ADR after the hour of hands-on, not before.
