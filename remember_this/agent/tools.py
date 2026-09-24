from pydantic_ai import RunContext

from remember_this.agent.agent import UserIdentifier, agent
from remember_this.llm.extraction import ExtractionResult, extract_facts
from remember_this.retrieval.embeddings import embed_text
from remember_this.db.repository import save_message_with_memories
from remember_this.llm.answer import Answer, generate_answer
from remember_this.retrieval.search import retrieve, RetrievalOutcome
from remember_this.observability.tracing import langfuse


@agent.tool
async def save_memories(
    ctx: RunContext[UserIdentifier],
    raw_message: str
) -> ExtractionResult:
    extraction_result: ExtractionResult = await extract_facts(raw_message)
    if not extraction_result.facts:
        return ExtractionResult(facts=[])

    facts: list[str] = [fact.fact_text for fact in extraction_result.facts]

    fact_embeddings: list[list[float]] = await embed_text(text_to_embed=facts)

    formatted_facts: list[tuple[str, list[float]]] = [
        (facts[i], fact_embeddings[i])
        for i in range(len(facts))
    ]

    with langfuse.start_as_current_observation(as_type="span", name="db.save_message_with_memories") as span:
        message_id = await save_message_with_memories(
            user_id=ctx.deps.get_user_id(),
            raw_text=raw_message,
            facts=formatted_facts
        )
        span.update(output={
            "message_id": message_id,
            "fact_count": len(formatted_facts)
        })

    return extraction_result


@agent.tool
async def search_memories(
    ctx: RunContext[UserIdentifier],
    question: str
) -> Answer:
    retrieval_outcome: RetrievalOutcome = await retrieve(
        user_id=ctx.deps.get_user_id(),
        question=question
    )

    if retrieval_outcome.abstain or not retrieval_outcome.matches:
        return Answer(
            answer_text="No answer found from memories",
            cited_memory_ids=[]
        )

    answer: Answer = await generate_answer(
        question=question,
        matches=retrieval_outcome.matches
    )
    return answer


