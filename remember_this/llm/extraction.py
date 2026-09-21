from pydantic import BaseModel

from remember_this.llm.client import create_agent
from remember_this.llm.prompts.extraction import fact_extraction_prompt


class ExtractedFact(BaseModel):
    fact_text: str


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact]


fact_extraction_agent = create_agent(
    model_key="llm_model",
    output_type=ExtractionResult,
    system_prompt=fact_extraction_prompt,
    temperature=0.2
)


async def extract_facts(raw_text: str) -> ExtractionResult:
    """Decompose a raw feed message into atomic facts.

    Deliberately does not catch failures from agent.run(): if Pydantic AI's own
    validation retries are exhausted and the model still can't produce a valid
    ExtractionResult, the exception propagates.
    """
    if not raw_text or not raw_text.strip():
        return ExtractionResult(facts=[])

    result = await fact_extraction_agent.run(raw_text)
    return result.output
