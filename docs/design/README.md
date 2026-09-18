# remember-this — System Design Phase Breakdown

A Telegram bot that stores free-form natural language notes ("remember this...") and answers
questions about them precisely, driven end-to-end by an LLM.

The point of this repo is **not** the bot. The bot is the smallest interesting vehicle for
practising: agentic control flow, retrieval design, LLM observability, and LLM evaluation.
Every phase below is framed as a **decision to be made by you**, with the alternatives you
should read about before deciding. Nothing here prescribes an answer.

## Companion documents

- `constraints.md` — what is already fixed (LLM access, language, users, privacy posture). Read first.
- `phase-0-product-contract.md` — the locked v1 scope, correctness definition, and non-goals.
- `phase-1-interaction-model.md` — message taxonomy, routing, and command set.
- `phase-2-memory-representation.md` — what a memory is and what is stored.
- `phase-3-retrieval.md` — retrieval pipeline and the deferred experiment queue.
- `phase-4-control-flow.md` — agent shape, tools, loop bounds, framework.
- `phase-5-infrastructure.md` — deployment topology, datastore, cost budget.
- `phase-6-observability.md` — trace model, payload/privacy stance, feedback capture.
- `phase-7-evaluation.md` — dataset, metric suites, judges, judge validation, gating.
- `phase-8-safety-and-failure.md` — access, isolation, injection, failure behaviour.
- `phase-9-change-workflow.md` — prompt versioning, experiments, deploy, quota.
- `shortlists.md` — narrowed option sets for runtime/hosting and for the observability platform.
- `decisions/` — your ADRs, one per locked decision.

## How to use this document

1. Work phases roughly in order. Phases 0–5 define the system, 6–9 define how you know it works.
2. For each phase: read the alternatives, then write a short decision record in
   `docs/design/decisions/` (template in that folder) and mark the phase complete here.
3. Do not write code until a phase's **exit criteria** are met. Design-only, on purpose.
4. Revisiting a decision later is expected and is itself a resume-worthy artifact — record the
   revision rather than editing history.

## Track A vs Track B (important sequencing note)

Two things are being designed in parallel and they interleave:

- **Track A — the product**: Phases 0–5, 8. The bot itself.
- **Track B — the discipline**: Phases 6, 7, 9. Observability, evaluation, lifecycle.

The common failure mode in projects like this is building all of Track A and bolting Track B on
at the end. Track B is the part that makes this a portfolio project rather than a weekend toy.
Decide early (Phase 0 exit) how far left you want to shift it — e.g. whether you commit to
"no prompt change ships without an eval run" before there is a prompt to change.

---

## Phase 0 — Scope, product contract, and success definition

**The question:** What exactly does this bot promise to do, and how will you know it is doing it?

**Sub-decisions to lock:**
- The behaviours in v1 vs explicitly deferred (non-goals list).
- What correctness bar a handful of family members implies (see `constraints.md` C3, C4).
- What "precisely" means in "answers questions precisely" — this is the single most important
  definition in the project, because it becomes your eval target in Phase 7.
- The failure you least want: wrong-but-confident answers, missed memories, or slow answers.
  You cannot optimise for all three.

**Alternatives / concepts to study:**
- Framing recall quality as a product spec vs as a model metric.
- Explicit "I don't know" / abstention as a first-class product behaviour vs always answering.
- Definition-of-done styles: user-story acceptance criteria vs behavioural test cases vs golden
  transcripts.

**Exit criteria:** A one-page product contract: 5–10 concrete example interactions you commit to
handling, a non-goals list, and a written definition of a "correct answer" and a "wrong answer".

---

## Phase 1 — Interaction and intent model

**The question:** When a message arrives, how does the system decide what the user wants?

Every message is one of: something to store, a question to answer, a correction, a deletion, an
administrative action, or noise. Getting this wrong dominates perceived quality — the LLM never
gets a chance to be smart if the message was routed to the wrong path.

**Sub-decisions to lock:**
- Explicit interface (slash commands like `/remember`, `/ask`) vs implicit (pure natural language,
  the system infers intent) vs hybrid.
- Where intent classification lives: rules/regex, a cheap classifier call, the main agent's own
  reasoning, or Telegram UI affordances (buttons, reply-to).
- Conversation state: is each message independent, or is there multi-turn context? What is the
  session boundary and when does it expire?
- Ambiguity handling: guess and act, or ask a clarifying question. What is the cost of each?
- Corrections and contradictions: if the user says something that conflicts with an old memory,
  is that a new memory, an update, or a conflict to surface?

**Alternatives / concepts to study:**
- Intent classification vs tool/function calling as a routing mechanism.
- Single-agent-with-tools vs a router that dispatches to specialised prompts.
- Confidence thresholds and clarification loops; cost of a clarifying question vs a wrong action.
- Telegram-specific interaction primitives (commands, inline keyboards, replies, edited messages)
  and what they let you avoid inferring.

**Exit criteria:** A decision table mapping message categories → routing path → what happens on
low confidence. Plus: what you will log about routing so Phase 6 can measure it.

---

## Phase 2 — Memory representation

**The question:** What is stored when the user says "remember this"?

This is the design decision with the longest shadow. Retrieval quality, eval difficulty, and
migration pain all follow from it.

**Sub-decisions to lock:**
- Raw utterance verbatim, LLM-extracted structured facts, an LLM-written summary, or several of
  these side by side. What is the source of truth if they disagree?
- Granularity: one memory per message, or split a message into atomic facts. Who splits — LLM or
  rules?
- Metadata to attach at write time: timestamps, entities, categories/tags, source message id,
  user id, confidence. Extraction cost vs retrieval benefit.
- Temporal semantics: memories with an event time vs a recorded time; facts that expire; facts
  that supersede earlier facts ("I moved to Berlin").
- Mutability: append-only log with derived views, vs in-place update/delete. Implications for
  "forget that" and for auditability and debugging.
- Whether extraction happens synchronously on write or asynchronously after acknowledging.

**Alternatives / concepts to study:**
- Episodic vs semantic memory as an architectural split; memory hierarchies.
- Fact/triple extraction and knowledge-graph style memory vs flat document memory.
- Write-time enrichment vs read-time interpretation (do the work when storing, or when asked?)
  and how each shifts cost, latency, and failure modes.
- Bi-temporal data modelling and invalidation of superseded facts.
- Prior art worth reading critically, not copying: conversational memory layers, agent memory
  patterns in current agent frameworks, long-term-memory research.

**Exit criteria:** A written memory schema (fields and semantics, not DDL), the answer to
"what happens on contradiction", and 3–5 worked examples of real messages turned into stored
memories by hand.

---

## Phase 3 — Retrieval architecture

**The question:** Given a question, how are the right memories found?

**Sub-decisions to lock:**
- Retrieval mechanism: lexical/keyword, dense vector, structured/metadata filtering, or a hybrid.
- Query handling: use the raw question, or have the LLM rewrite/expand/decompose it first.
- Single-shot retrieval vs agentic/iterative retrieval where the model can search again after
  seeing results.
- How much is fed to the answering step: top-k, threshold, reranking, or "everything" (with a
  small corpus, brute-force over all memories is a legitimate design — decide deliberately, and
  decide when it stops being legitimate).
- Handling questions that need aggregation or reasoning across many memories rather than
  finding one ("how many times did I...", "what did I say about X over the last month").
- Grounding and citation: does the answer point back to source memories? Is that user-visible?
- Abstention: what happens when retrieval finds nothing relevant.

**Alternatives / concepts to study:**
- Naive RAG vs hybrid search vs reranking vs agentic RAG; where each stops paying off.
- Embedding choice as a design constraint (dimension, cost, multilingual, re-embedding cost).
- Query decomposition, HyDE, step-back prompting — and their latency/cost price.
- Retrieval metrics (recall@k, MRR, nDCG) vs end-to-end answer metrics: which one you will
  actually optimise, and why measuring only the second makes debugging hard.
- Long-context stuffing as an alternative to retrieval, and its failure modes.

**Exit criteria:** A retrieval pipeline diagram with each stage's purpose, the failure mode each
stage exists to prevent, and the metric that will tell you whether each stage earns its place.

---

## Phase 4 — Agent control flow

**The question:** What is the shape of the thing that runs? A pipeline, an agent, or a graph?

**Sub-decisions to lock:**
- Fixed pipeline (deterministic steps) vs tool-calling agent (model decides the steps) vs a
  hybrid state machine with LLM decisions at specific nodes.
- Tool boundaries: what capabilities does the model get (`save_memory`, `search_memories`,
  `update_memory`, `delete_memory`, ...) and what stays outside the model's control.
- Number of LLM calls per turn and where the model is allowed to loop. Loop bounds and
  termination conditions.
- Model selection strategy: one model everywhere vs cheap-model-for-routing/expensive-for-answers;
  how you would swap providers.
- Prompt architecture: where prompts live, how they are versioned, and how variants are selected
  (this connects directly to Phase 9).
- Framework vs hand-rolled: what you gain in speed vs what you lose in visibility and in
  "I can explain every layer of this in an interview".

**Alternatives / concepts to study:**
- Workflow vs agent as an architectural choice, and the common patterns (chaining, routing,
  parallelisation, reflection, tool use).
- Structured output / constrained decoding vs free-text parsing.
- Agent frameworks (LangGraph, Pydantic AI, Agents SDK, plain function calling) compared on
  what they do to your observability story, not on their feature lists.
- Determinism and reproducibility: what makes a run replayable, which matters for Phase 7.

**Exit criteria:** A control-flow diagram for the two main paths (store, recall), a list of tools
with their contracts, the per-turn LLM call budget, and an explicit stance on frameworks.

---

## Phase 5 — Storage, deployment, and infrastructure topology

**The question:** Where does state live, where does code run, and what does the free tier allow?

**Sub-decisions to lock:**
Candidate options for the first three sub-decisions are narrowed in `shortlists.md` §1.

- Telegram integration: long polling vs webhook. Decide this first — it constrains hosting.
- Compute model: always-on small instance, serverless functions, or container on a
  scale-to-zero platform. Cold starts vs idle cost vs free-tier limits.
- Datastore(s): relational with a vector extension, dedicated vector DB, embedded/file-based,
  or two stores. One store vs two, and the operational cost of the second.
- Bot library and how much of its internals you are willing to trace around.
- Sync vs async processing: acknowledge immediately and process in the background, or process
  inline. Do you need a queue, or is that overkill at your scale?
- Secrets, config, and environment separation (dev vs prod bot tokens).
- Backup and data durability — free tiers delete idle databases; know that before your family
  loses their memories.
- Explicit scale assumptions: users, messages/day, memories/user. Write them down; they justify
  every "no, that's overkill" decision you make.

**Alternatives / concepts to study:**
- Free-tier landscape and its traps (idle suspension, egress, row limits, sleep-on-inactivity).
- Stateless vs stateful service design and why it constrains your hosting options.
- Vector storage options along the axes of cost, ops burden, filtering support, and lock-in.
- Local-first development and how you will run the whole system on your laptop.

**Exit criteria:** A deployment diagram, a written scale/cost budget, the free-tier limits you are
betting on, and a one-line answer to "what happens to the data if this platform shuts down".

---

## Phase 6 — Observability

**The question:** When a user says "it gave me a wrong answer", how do you find out why in
under five minutes?

This is a primary learning goal, so design it as a first-class subsystem rather than as logging.

**Sub-decisions to lock:**
- The unit of observation: trace per message, spans per step. What is a span in your system and
  what attributes does each carry.
- What gets captured: prompts, completions, retrieved memory ids, token counts, latency per step,
  model/prompt version, tool calls and their arguments, errors, routing decisions, retrieval scores.
- Instrumentation approach: OpenTelemetry-based / vendor SDK / auto-instrumentation / manual
  decorators. What happens to your data if you change vendors.
- Where traces go and what the retention story is on a free tier.
- PII and privacy: these are people's personal memories. Redact, hash, sample, self-host, or
  accept. Real tradeoff against debuggability; see `constraints.md` C6 for the agreed posture and
  the one-paragraph deliverable it demands.
- User feedback capture: thumbs up/down in Telegram, implicit signals (rephrased question =
  probable failure), or none. Feedback is what turns traces into an eval dataset in Phase 7.
- Operational signals worth alerting on vs merely recording: cost per day, error rate, p95
  latency, abstention rate, empty-retrieval rate.

**Alternatives / concepts to study:**
- Tracing for LLM apps vs conventional APM; why spans-with-payloads matters here.
- OpenTelemetry GenAI semantic conventions and the portability argument.
- Platform choice: shortlisted to three in `shortlists.md` §2, with the axes to judge them on and a
  suggested hands-on trial rather than a paper comparison.
- Online evaluation / production monitoring: LLM-as-judge scoring on live traffic, sampling
  strategies, guardrail metrics.
- The trace → dataset → eval → improved prompt → new trace loop as a single system, since this
  is the loop the whole project exists to demonstrate.

**Exit criteria:** A spec of your trace/span model with attribute names, the chosen platform and
why, your PII stance, and the specific debugging workflow you will follow on a user complaint.

---

## Phase 7 — Evaluation

**The question:** How do you know a change made the system better rather than different?

**Sub-decisions to lock:**
- What you evaluate: individual components (intent routing, extraction, retrieval) vs end-to-end
  answers vs both. Component evals localise bugs; end-to-end evals reflect user experience.
- Dataset strategy: hand-written golden cases, synthetically generated cases, cases harvested
  from production traces, or all three. How large, and how it grows over time.
- Ground truth: exact expected answer, expected memory ids, a rubric, or pairwise preference.
- Metrics: deterministic (exact match, retrieval recall, latency, cost) vs model-graded
  (faithfulness, relevance, completeness, correctness-against-reference).
- LLM-as-judge design if used: judge model, rubric, scoring scale, position/verbosity bias
  mitigation, and how you validate that the judge agrees with you. An unvalidated judge is a
  random number generator with good PR.
- Adversarial and edge cases you deliberately include: contradictions, temporal questions,
  nothing-stored questions, multi-hop questions, non-English or mixed-language input, typos.
- When evals run: locally on demand, on every commit in CI, pre-deploy gate, nightly on
  production samples. Pass/fail thresholds and what happens on regression.
- Cost and runtime budget for a full eval run — if it is slow or expensive, you will stop
  running it, and the whole discipline collapses.

**Alternatives / concepts to study:**
- Offline vs online evaluation; the role of each in a change workflow.
- RAG-specific eval frameworks and metrics (RAGAS-style faithfulness/relevance, retrieval vs
  generation attribution) and their known weaknesses.
- Judge validation: agreement with human labels, Cohen's kappa, calibration.
- Regression testing for non-deterministic systems: seeds, temperature, tolerance bands,
  statistical significance with small datasets.
- Experiment tracking and comparing runs across prompt/model versions.

**Exit criteria:** An eval plan naming each eval suite, its dataset, its metrics, its thresholds,
where it runs, and how the dataset grows from production traces.

---

## Phase 8 — Multi-tenancy, safety, and failure behaviour

**The question:** What happens when things go wrong, and what stops user A seeing user B's
memories?

**Sub-decisions to lock:**
- Isolation model: how user identity flows from Telegram through to every query, and where that
  is enforced (application code, database policy, or both). DM-only scope (C3) makes ownership
  unambiguous, so this is about enforcement discipline rather than a permission model.
- Access control: allowlist of Telegram user ids vs open to anyone. With university-provided LLM
  access (C1) the exposure is quota abuse and acceptable-use, not your credit card.
- Prompt injection through stored memories: a memory is untrusted user content that later lands
  in a prompt. Decide whether you treat it as data or as instructions, and how you enforce that.
- Failure behaviour per dependency: LLM API down/rate-limited/slow, database unavailable,
  Telegram delivery failure. Retry, degrade, or apologise clearly.
- Rate limiting and cost caps per user, and what the user sees when they hit one.
- Data rights: can a user export or delete everything? Where does deleted data actually go
  (including your trace store from Phase 6)?

**Alternatives / concepts to study:**
- Tenant isolation patterns and row-level security.
- Prompt injection defences: delimiting, structured inputs, privilege separation, output
  filtering, and their honest limits.
- Idempotency and duplicate delivery from webhooks/retries.
- Graceful degradation patterns and user-facing error design.

**Exit criteria:** A threat/failure table: what can go wrong, what the system does, what the user
sees. Plus the enforcement point for isolation, stated precisely.

---

## Phase 9 — Change workflow and lifecycle

**The question:** How does an improvement travel from idea to production, and back out if wrong?

**Sub-decisions to lock:**
- Prompt management: in code and versioned with git, or in a platform's prompt registry with
  runtime fetching. Tradeoff: reviewability and atomic deploys vs iteration speed and
  non-code editing.
- Change gate: what must pass before a prompt or model change ships.
- Experimentation: offline A/B on a dataset only, or live traffic splitting. Is live
  experimentation meaningful at your user count?
- Model/provider upgrades: how you re-baseline when the underlying model changes under you.
- Cost and usage monitoring, and a kill switch.
- What is documented for a reader of the repo: architecture decision records, an eval report, a
  screenshot of a trace. These artifacts are the resume payload.

**Alternatives / concepts to study:**
- Prompt versioning and deployment patterns; treating prompts as config vs as code.
- CI for LLM apps: what belongs in a pull-request check vs a nightly job.
- Canary/shadow deployment for model changes.
- ADR practice as lightweight design documentation.

**Exit criteria:** A written change workflow ("to change a prompt, I do X, Y, Z, and it ships if
W"), and a list of the artifacts the repo will contain to prove the discipline exists.

---

## Phase 10 — Demonstration narrative

**The question:** What does someone see in ten minutes that convinces them you can build and
operate LLM systems?

Not an afterthought — knowing the target shapes earlier phases. Candidate artifacts to choose
between: architecture and trace diagrams, an eval report with before/after numbers on a real
regression, a documented incident ("it answered wrong, here is the trace, here is the fix, here
is the eval case that now guards it"), a cost/latency table, the ADR trail itself.

**Exit criteria:** A README outline and a shortlist of artifacts, each mapped to the skill it
evidences.

---

## The system, in one paragraph

A Telegram DM bot on Cloud Run, woken by webhook, processing each turn inside the request. A Pydantic AI agent
with three tools routes each message: its tool choice is the intent classification. Feed messages are split by
LLM extraction into atomic facts, stored append-only in Neon Postgres alongside the verbatim original, and echoed
back as a confirmation. Questions are embedded verbatim and matched by pgvector against a strict similarity
threshold; a miss triggers one relaxed-threshold retry adjudicated by an LLM relevance check, and abstention only
if that rejects too. Answers cite the memory and date they came from. Everything is traced to Langfuse with full
payloads and hashed user ids, with thumbs up/down feeding an eval dataset of generated-and-reviewed cases scored
by nine metric suites and judged by a different model than the one being judged. Changes ship on a git tag, after
a local eval run shows no regression.

## Progress tracker

| Phase | Topic | Status | Decision record |
|---|---|---|---|
| 0 | Scope & success definition | **done** — `phase-0-product-contract.md` | ADR-001 |
| 1 | Interaction & intent model | **done** — `phase-1-interaction-model.md` | ADR-002 |
| 2 | Memory representation | **done** — `phase-2-memory-representation.md` | ADR-003 |
| 3 | Retrieval architecture | **done** — `phase-3-retrieval.md` | ADR-004 |
| 4 | Agent control flow | **done** — `phase-4-control-flow.md` | ADR-005 |
| 5 | Storage & infrastructure | **done** — `phase-5-infrastructure.md` | ADR-006 |
| 6 | Observability | **done** — `phase-6-observability.md` | ADR-007 |
| 7 | Evaluation | **done** — `phase-7-evaluation.md` | ADR-008 |
| 8 | Multi-tenancy, safety, failure | **done** — `phase-8-safety-and-failure.md` | ADR-009 |
| 9 | Change workflow & lifecycle | **done** — `phase-9-change-workflow.md` | ADR-010 |
| 10 | Demonstration narrative | deferred until after build | |

## Scope discipline

This project is deliberately small. Two guardrails against over-engineering:

- Every component must be justified by a failure it prevents or a metric it improves. If you
  cannot name one, cut it.
- Prefer the simplest option that you can still *measure*. Sophistication is only defensible
  once you can show the simple version falling short — and showing that is more impressive than
  having built the complex thing by default.
