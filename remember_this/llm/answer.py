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
    temperature=0.0
)

async def generate_answer(
    question: str,
    matches: list[MemoryMatch]
) -> Answer:
    """Compose an answer from facts already judged usable by retrieve().
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
