from pydantic import BaseModel, Field

from remember_this.models import MemoryMatch
from remember_this.llm.relevance import RelevanceVerdict, check_relevance
from remember_this.retrieval.embeddings import embed_text
from remember_this.db.repository import search_memories
from remember_this.config import get_settings

Settings = get_settings()

class RetrievalOutcome(BaseModel):
    matches: list[MemoryMatch] = Field(default_factory=list)
    abstain: bool
    retry_occured: bool
    relevance_verdict: RelevanceVerdict | None = None


async def retrieve(user_id: int, question: str) -> RetrievalOutcome:
    # embed_text takes/returns a list (batch-friendly); a single question is a batch of one.
    [question_embedding] = await embed_text(text_to_embed=[question])

    primary_candidates: list[MemoryMatch] = await search_memories(
        user_id=user_id,
        query_embedding=question_embedding,
        threshold=Settings.strict_threshold,
        limit=Settings.embedding_retrieval_limit
    )
    if len(primary_candidates) > 0:
        return RetrievalOutcome(
            matches=primary_candidates,
            abstain=False,
            retry_occured=False
        )

    secondary_candidates: list[MemoryMatch] = await search_memories(
        user_id=user_id,
        query_embedding=question_embedding,
        threshold=Settings.relaxed_threshold,
        limit=Settings.embedding_retrieval_limit
    )
    if len(secondary_candidates) == 0:
        return RetrievalOutcome(
            matches=[],
            abstain=True,
            retry_occured=True
        )

    relevance_verdict: RelevanceVerdict = await check_relevance(
        question=question,
        candidate_facts=[candidate.fact_text for candidate in secondary_candidates]
    )
    if relevance_verdict.can_answer:
        return RetrievalOutcome(
            matches=secondary_candidates,
            abstain=False,
            retry_occured=True,
            relevance_verdict=relevance_verdict
        )

    return RetrievalOutcome(
        matches=[],
        abstain=True,
        retry_occured=True,
        relevance_verdict=relevance_verdict
    )
