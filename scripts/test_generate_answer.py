"""Throwaway manual test for remember_this.llm.answer.generate_answer.

Each case constructs MemoryMatch objects by hand (no DB, no retrieval) and targets one
specific rule from prompts/answer.py. Not the real eval harness -- read the answer_text
and cited_memory_ids by hand for each case.

Run from the repo root:
    uv run python -m scripts.test_generate_answer
"""

import asyncio
from datetime import datetime, timezone

from remember_this.llm.answer import generate_answer
from remember_this.models import MemoryMatch


def m(id: int, fact_text: str, similarity: float = 0.9) -> MemoryMatch:
    return MemoryMatch(
        id=id,
        fact_text=fact_text,
        created_at=datetime.now(timezone.utc),
        similarity=similarity,
    )


CASES = [
    (
        "1. Direct match, verbatim identifier",
        "What is my student id?",
        [m(1, "Student id is ABCDEF")],
        "Expect: 'ABCDEF' exact case, cited_memory_ids=[1].",
    ),
    (
        "2. Inference-based match (rule 2) -- stated confidently, not hedged",
        "What pizza places have I been to?",
        [m(2, "Garlic bread at Domino's was average")],
        "Expect: states Domino's is/was a pizza place directly, no 'possibly'/'might be' hedging, "
        "cited_memory_ids=[2].",
    ),
    (
        "3. Decoy fact provided, must be excluded from citation",
        "What is my student id?",
        [m(1, "Student id is ABCDEF"), m(3, "Rent is 1450, due on the 1st")],
        "Expect: answers only the student id, cited_memory_ids=[1] only, id 3 never mentioned.",
    ),
    (
        "4. Two facts genuinely both needed, no third-fact padding",
        "When is my exam and what's my student id?",
        [
            m(1, "Student id is ABCDEF"),
            m(4, "Final exam ends on Nov 30"),
            m(3, "Rent is 1450, due on the 1st"),
        ],
        "Expect: both exam date and student id present, cited_memory_ids=[1, 4] (order may vary), "
        "id 3 excluded, no mention of rent.",
    ),
    (
        "5. Multiple facts about same entity, must pick the one that actually answers",
        "What did I not like at Rosetta's?",
        [m(5, "Visited Rosetta's"), m(6, "Mac and cheese at Rosetta's was bad")],
        "Expect: answer is specifically about the mac and cheese, cited_memory_ids=[6] only "
        "(id 5 states a fact but doesn't answer 'what did I dislike').",
    ),
    (
        "6. Near-duplicate facts with a real internal conflict",
        "What time is the meeting?",
        [m(7, "Meeting with Raj is at 3pm"), m(8, "Meeting with Raj moved to 4pm")],
        "Genuinely ambiguous - there's no way to know which is newer from this input alone (rule 6 "
        "territory, but also a preview of the latest-value problem this project has scoped out). "
        "Worth seeing which one it picks and whether it notices the conflict at all, or silently "
        "picks one without flagging it.",
    ),
    (
        "7. Question narrower than the fact provided",
        "What's my exam date?",
        [m(9, "Final exam ends on Nov 30 and starts on Nov 25")],
        "Expect: answers with Nov 30 (or clarifies start vs end) without inventing which one was "
        "asked for -- tests whether it over-answers by dumping both dates when the question likely "
        "means the end date, or under-answers by picking the wrong one silently.",
    ),
    (
        "8. Fact requires an inference the model should NOT make (occasion-specific, not entity-fixed)",
        "Did I eat pizza at Domino's?",
        [m(2, "Garlic bread at Domino's was average")],
        "Trap case: this fact should NOT have passed the relevance/retrieval gate for this exact "
        "question in the real pipeline (per relevance.py rule 2a, 'ate pizza' is occasion-specific, "
        "not a fixed property). But if it somehow reaches generate_answer anyway, does the model "
        "correctly avoid claiming pizza was eaten, or does it wrongly say yes because Domino's sells "
        "pizza? This tests whether the answer step has its own defense or purely trusts the input.",
    ),
    (
        "9. Verbatim fidelity under formatting pressure",
        "What's the wifi password and my flight number?",
        [m(10, "wifi password is Sunshine123"), m(11, "flight is UA 1823")],
        "Expect: 'Sunshine123' and 'UA 1823' reproduced with exact case/spacing, not reformatted "
        "(e.g. not 'sunshine123' or 'UA1823'), cited_memory_ids=[10, 11].",
    ),
    (
        "10. Single fact, multi-part question, only part of it answerable",
        "What's my student id and my passport number?",
        [m(1, "Student id is ABCDEF")],
        "Trap case: passport number was never provided as a fact. Expect: answers only the student "
        "id, does NOT invent a passport number, and ideally notes the passport number wasn't found -- "
        "though note generate_answer's contract assumes matches are already relevant, so a real "
        "pipeline might never construct this exact input. Still useful to see how it behaves.",
    ),
]


async def main() -> None:
    for label, question, matches, note in CASES:
        result = await generate_answer(question, matches)
        print(f"\n{'=' * 100}")
        print(label)
        print(f"  question:          {question}")
        print(f"  facts provided:    {[(mm.id, mm.fact_text) for mm in matches]}")
        print(f"  note:              {note}")
        print(f"  answer_text:       {result.answer_text}")
        print(f"  cited_memory_ids:  {result.cited_memory_ids}")


if __name__ == "__main__":
    asyncio.run(main())
