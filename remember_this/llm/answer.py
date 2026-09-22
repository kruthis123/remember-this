from pydantic import BaseModel

from remember_this.llm.client import create_agent
from remember_this.llm.prompts.answer import answer_prompt
from remember_this.models import MemoryMatch

class Answer(BaseModel):
    answer_text: str
    cited_memory_ids: list[int]

answer_agent = create_agent(
    model_key="llm_model",
    output_type=Answer,
    system_prompt=answer_prompt,
    temperature=0.2
)

async def generate_answer(
    question: str,
    matches: list[MemoryMatch]
) -> Answer:
    """Compose an answer from facts already judged usable by retrieve().

    This function does not decide abstention -- that decision belongs entirely to
    retrieve() (see docs/build/step-05-answer-generation.md Part 0). Calling this
    with an empty `matches` list is a caller bug, not a valid input, so it fails
    loudly instead of returning a graceful fallback that would hide the bug and
    create a second place abstention could happen.
    """
    if not matches:
        raise ValueError(
            "generate_answer() called with no matches. The caller must check "
            "RetrievalOutcome.abstain before calling this function."
        )

    facts_block = "\n".join(f"(id={match.id}) {match.fact_text}" for match in matches)
    user_prompt = f"Question: {question}\n\nFacts:\n{facts_block}"

    result = await answer_agent.run(user_prompt)
    return result.output
