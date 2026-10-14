"""Deterministic eval metrics. No LLM calls, no judge model.

Each function takes a case (a dict loaded from one of evals/data/generated/*.json)
and a TurnResult (remember_this.agent.runner.run_turn's return value) from running
that case's question through the real system, and returns True/False, or None when
the metric doesn't apply to that case.
"""

from remember_this.agent.runner import TurnResult
from remember_this.db import repository as db


def verbatim_fidelity(case: dict, turn: TurnResult) -> bool | None:
    """Exact, case-sensitive substring check. Only meaningful when the case's
    reference_answer is itself a literal value (an id, a code, a name) rather than
    a sentence -- see each case file's `check_verbatim` field.
    """
    if not case.get("check_verbatim"):
        return None
    return case["reference_answer"] in turn.reply



# Every borderline_relevance case is designed so a correct answer cites a real
# memory to explain the absence (a cancelled event, a declined offer, someone
# else's opinion) rather than reporting plain absence -- see each case's own
# notes in 07_borderline_relevance.json. The near_miss_partial abstention variant
# is the same shape (cites the date when only the time is missing). For all of
# these, TurnResult.abstained (empty citation) does not line up with
# expect_abstention even when the answer is correct, so this metric cannot speak
# to them -- use the correctness judge instead.
_CITED_ABSTENTION_VARIANTS = {"near_miss_partial"}


def abstention_correctness(case: dict, turn: TurnResult) -> bool | None:
    """Compares case["expect_abstention"] against TurnResult.abstained, which is
    derived from the tool's own return value (empty citations on a search_memories
    turn), not from matching phrases in the reply text -- a correct abstention can
    be worded many ways and won't reliably contain any fixed phrase.

    Returns None for cases where a correct answer is expected to cite a fact even
    though expect_abstention is true (see _CITED_ABSTENTION_VARIANTS and the
    borderline_relevance category check below).
    """
    if case["category"] == "borderline_relevance":
        return None
    if case.get("variant") in _CITED_ABSTENTION_VARIANTS:
        return None
    return case["expect_abstention"] == bool(turn.abstained)


async def attribution(turn: TurnResult) -> bool | None:
    """Checks that every id in turn.cited_memory_ids refers to a memory that
    actually exists. Only applies to a search_memories turn with at least one
    citation.

    Known limitation: this only catches an invented id that doesn't exist at all.
    It does NOT catch a real id cited for the wrong reason (a memory that exists
    but doesn't actually support the answer) -- that needs the full list of ids
    retrieve() considered, which isn't threaded through TurnResult.
    """
    if turn.tool_called != "search_memories":
        return None
    if not turn.cited_memory_ids:
        return None
    rows = await db._get_pool().fetch(
        "SELECT id FROM memories WHERE id = ANY($1)",
        turn.cited_memory_ids,
    )
    return len(rows) == len(turn.cited_memory_ids)


def routing(turn: TurnResult) -> bool:
    """Every case's question turn is expected to route to search_memories --
    including abstention cases, since abstaining is still a search_memories
    outcome. Feed/seeding turns are save_memories by construction and aren't
    checked here.
    """
    return turn.tool_called == "search_memories"
