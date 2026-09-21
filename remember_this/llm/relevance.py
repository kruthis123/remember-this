from pydantic import BaseModel

from remember_this.llm.client import create_agent
from remember_this.llm.prompts.relevance import relevance_check_prompt

import asyncio

class RelevanceVerdict(BaseModel):
    can_answer: bool
    reasoning: str

relevance_check_agent = create_agent(
    model_key="llm_model",
    output_type=RelevanceVerdict,
    system_prompt=relevance_check_prompt,
    temperature=0.2
)

async def check_relevance(
    question: str,
    candidate_facts: list[str]
) -> RelevanceVerdict:
    if not candidate_facts or not len(candidate_facts):
        return RelevanceVerdict(
            can_answer=False,
            reasoning="No matching candidates"
        )
    
    result = await relevance_check_agent.run(
        f"User question - {question}" + f"Candidate facts - {candidate_facts}"
    )
    return result.output