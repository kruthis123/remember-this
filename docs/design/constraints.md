# Fixed constraints

Things already settled. These are inputs to the phase decisions in `README.md`, not decisions
themselves. Anything not listed here is still open.

| # | Constraint | Consequence for design |
|---|---|---|
| C1 | LLM access via university-hosted, OpenAI-SDK-compatible endpoints, including embeddings | No provider billing pressure, but rate limits, model availability, and uptime are outside your control. Treat the provider as a dependency that can change or vanish: keep the client behind a thin seam (Phase 4), and record model identity on every trace (Phase 6) so results stay interpretable if models are swapped underneath you. |
| C2 | Python | Ecosystem for tracing/eval is strongest here, so no tooling is ruled out. Runtime and library choices are still open — see `shortlists.md`. |
| C3 | One-to-one DMs only; no group chats | Memory ownership is unambiguous: one Telegram user id owns their memories. Simplifies Phase 1 (no addressing problem) and Phase 8 (isolation is a single-column filter, not a permission model). |
| C4 | A handful of trusted users (family), ~4 weekends of effort | Justifies rejecting queues, sharding, caching layers, and multi-region anything. Also means production traffic will be too sparse to learn from statistically — your eval dataset must be deliberately constructed (Phase 7), not harvested passively. |
| C5 | Observability/eval platform: pick from a shortlist rather than surveying the field | See `shortlists.md`. Decide by Phase 6, but read it before Phase 4, because the platform's SDK shape can influence how you structure the agent. |
| C6 | Privacy considered, not maximised | See below. |
| C7 | Model inventory fixed by the provider | See below. Three chat families, one embedding model, uncapped usage. |

## On C6 — the privacy posture

The tension is real and worth resolving explicitly rather than by drift: traces are only useful for
debugging if they contain the actual prompts and completions, and here those contain family
members' personal notes. Full redaction would gut Phase 6; ignoring it entirely is a bad look on a
project whose selling point is operational maturity.

The proportionate framing for this project: decide **where personal content is allowed to land**,
write that down once, and let it constrain the platform choice. Cheap measures that buy most of the
benefit — user ids as opaque identifiers rather than names, a stated retention window, self-hosting
if the platform makes it trivial, a `/forget` path that also covers derived data, telling your users
what is stored — are proportionate. Field-level encryption, PII detection pipelines, and audit logs
are not, at five users.

Deliverable in Phase 6: one paragraph in the README stating what is stored, where, for how long,
and how a user deletes it. That paragraph is itself the artifact.

## On C7 — available models and role assignment

The provider exposes three distinct chat families (Gemma, Llama, Qwen — plus Ornith, described as
agentic-coding, lineage unclear) and exactly one embedding model. Usage is uncapped, so the zero-cost-pressure
assumption behind ADR-001 and ADR-008 holds despite the per-token rates published in the model list.

| Role | Model | Reason |
|---|---|---|
| System (all four reasoning steps) | `qwen3.6:35b` | agentic-oriented, 262k context, best tool-calling prospect |
| Judge (Phase 7) | `gemma4:26b` | different family from the system model, which is what actually mitigates self-preference bias |
| Distractor generator | `llama3.1:8b` | third family, and quality is irrelevant for filler |
| Embeddings | `bge-m3` | the only option |

**Labelled eval cases are authored by Claude (this assistant), not by a provider model.** A fourth family gives
better independence than `llama3.1:8b`, and case quality is what determines whether the metrics mean anything.
The generator model is retained for the bulk distractor corpus, so the repo still contains a real generation
pipeline. Generator and judge must never be the same model — a judge grading against references it wrote itself
is the worst available coupling.

Consequences to carry forward:

- **One embedding model means embedding comparison is off the Phase 3 experiment queue.** Remaining retrieval
  experiments: threshold sweep, query rewriting, reranking, hybrid.
- **`bge-m3` emits 1024-dimensional vectors**, which fixes the vector column width in the schema.
- **No model advertises function calling or JSON-schema output.** ADR-005 depends on structured output entirely,
  so this must be verified against `qwen3.6:35b` before the agent is built. Fallback if schema mode is absent:
  tool-call-based structured output via Pydantic AI.
- **Case authorship by an assistant that has read the design docs** carries a mild risk of cases that flatter the
  design. Human review and the adversarial categories in `phase-7-evaluation.md` are the check.

## Non-constraints worth stating

- No cost pressure on LLM calls (C1) makes multi-call designs and LLM-as-judge affordable. Guard
  against the failure mode this invites: adding LLM calls because they are free rather than because
  they measurably help. Phase 7 exists to keep that honest.
- Sparse real traffic (C4) means latency and throughput are near-irrelevant as engineering
  problems, but still worth *measuring*, because measuring them is the demonstrable skill.
