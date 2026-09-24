"""Adapt the in-scope subset of LongMemEval into remember-this's eval format.

LongMemEval (ICLR 2025, Wu et al., arXiv:2410.10813) evaluates chat-assistant
long-term memory over multi-session conversation histories. Most of it is out of
scope for this project (see SCOPE NOTES below), but its `single-session-user`
slice is structurally identical to remember-this's point-lookup contract: a user
states a fact in passing inside a longer multi-topic message, and a later
question asks for that fact precisely.

Using it instead of a self-authored dataset removes the self-authorship bias
recorded in docs/design/constraints.md C7 -- these cases were written by someone
with no knowledge of this system's prompts or design.

    Source: https://github.com/xiaowu0162/LongMemEval
    Data:   https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
            (longmemeval_oracle.json -- the oracle-retrieval variant, which
             includes only evidence sessions rather than the full haystack)

LICENCE: no explicit licence file was found for the dataset at time of writing.
Treat as research-use-only until verified. Cite the paper in any writeup.

SCOPE NOTES -- what is included and why the rest is not:

  INCLUDED
    single-session-user (64 non-abstention)
        A fact stated by the user in one session, asked back later. Exactly the
        point-lookup case from docs/design/phase-0-product-contract.md.
    single-session-user (6 abstention, `_abs` suffix)
        Question about something never mentioned. Directly exercises the
        false-abstention gate from Phase 0 / ADR-001.

  EXCLUDED
    knowledge-update (78)
        Latest-value lookup. Explicit non-goal (ADR-003: append-only, no
        supersession; contradictions stored side by side).
    multi-session (133)
        Aggregate / multi-hop reasoning across memories. Explicit non-goal
        (ADR-001, phase-0-product-contract.md).
    temporal-reasoning (133)
        Requires temporal ordering/arithmetic over memories. ADR-003 stores
        created_at but deliberately builds no temporal reasoning on it.
    single-session-assistant (56)
        The fact originates in an ASSISTANT turn. remember-this only stores
        facts the user asserts about themselves, so there is nothing to store.
    single-session-preference (30)
        The "answer" describes a preferred response *style*, not a recallable
        fact -- it evaluates personalization, not memory recall.
    abstention instances of the above types (24)
        Their questions presuppose out-of-scope capabilities (e.g. "which did I
        do first"), so abstaining for the right reason is untestable here.

USAGE
    1. Download the source data:
         mkdir -p evals/data/source
         curl -L -o evals/data/source/longmemeval_oracle.json \\
           https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_oracle.json
    2. Run this adapter:
         uv run python -m evals.generate.adapt_longmemeval
    3. Review the output at evals/data/longmemeval_in_scope.json by hand before
       trusting it (see the REVIEW REQUIRED note below).

REVIEW REQUIRED -- this adapter does NOT produce a trustworthy dataset on its own:
  - It keeps only USER turns, discarding assistant turns. For single-session-user
    the evidence is in a user turn by construction, but some questions may still
    lean on assistant-provided context. Spot-check a sample.
  - LongMemEval answers are short reference strings written for an LLM judge, not
    for exact match. They are reference answers, not expected literal output.
  - Some questions may still be subtly out of scope in ways the type label
    doesn't capture. Read them.
"""

import json
from pathlib import Path

SOURCE = Path("evals/data/source/longmemeval_oracle.json")
DEST = Path("evals/data/longmemeval_in_scope.json")

IN_SCOPE_TYPE = "single-session-user"


def adapt() -> None:
    if not SOURCE.exists():
        raise SystemExit(
            f"Source not found: {SOURCE}\n"
            "Download it first -- see the USAGE section in this file's docstring."
        )

    raw = json.loads(SOURCE.read_text(encoding="utf-8"))

    cases = []
    skipped_no_evidence = 0

    for item in raw:
        if item["question_type"] != IN_SCOPE_TYPE:
            continue

        is_abstention = item["question_id"].endswith("_abs")

        # Collect the user turns that will be fed to the bot as feed messages,
        # and separately note which of them carry the answer -- that flag is the
        # retrieval ground truth (ADR-008 wants expected memory ids; this is the
        # upstream equivalent, since our memory ids don't exist until we store).
        feed_messages = []
        evidence_indices = []
        for session in item["haystack_sessions"]:
            for turn in session:
                if turn["role"] != "user":
                    continue
                if turn.get("has_answer"):
                    evidence_indices.append(len(feed_messages))
                feed_messages.append(turn["content"])

        if not feed_messages:
            skipped_no_evidence += 1
            continue

        # A non-abstention case with no flagged evidence turn would give us no
        # retrieval ground truth, so it's not usable for the retrieval metric.
        if not is_abstention and not evidence_indices:
            skipped_no_evidence += 1
            continue

        cases.append(
            {
                "case_id": item["question_id"],
                "source": "longmemeval",
                "source_question_type": item["question_type"],
                "category": "abstention" if is_abstention else "point_lookup",
                "feed_messages": feed_messages,
                "evidence_feed_indices": evidence_indices,
                "question": item["question"],
                "reference_answer": item["answer"],
                "expect_abstention": is_abstention,
                "question_date": item.get("question_date"),
                "reviewed": False,
                "review_notes": "",
            }
        )

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")

    n_abs = sum(1 for c in cases if c["expect_abstention"])
    print(f"wrote {len(cases)} cases to {DEST}")
    print(f"  point_lookup: {len(cases) - n_abs}")
    print(f"  abstention:   {n_abs}")
    if skipped_no_evidence:
        print(f"  skipped (no usable evidence turn): {skipped_no_evidence}")
    print()
    print("NOT YET REVIEWED. Every case has reviewed=false -- read them before use.")
    print("See the REVIEW REQUIRED note in this file's docstring.")


if __name__ == "__main__":
    adapt()
