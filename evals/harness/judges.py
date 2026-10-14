from typing import Literal

from pydantic import BaseModel

from evals.harness.judge_prompts import correctness_judge_prompt, faithfulness_judge_prompt
from remember_this.llm.client import create_agent


class FaithfulnessVerdict(BaseModel):
    # Reasoning comes before the verdict so the model works through the claims before committing to a label.
    reasoning: str
    unsupported_claims: list[str]
    verdict: Literal["faithful", "unfaithful"]


class CorrectnessVerdict(BaseModel):
    reasoning: str
    verdict: Literal["correct", "partial", "incorrect"]


faithfulness_agent = create_agent(
    model_key="judge_model",
    output_type=FaithfulnessVerdict,
    system_prompt=faithfulness_judge_prompt,
    temperature=0.0,
)

correctness_agent = create_agent(
    model_key="judge_model",
    output_type=CorrectnessVerdict,
    system_prompt=correctness_judge_prompt,
    temperature=0.0,
)


def _format_facts(stored_facts: list[str]) -> str:
    if not stored_facts:
        return "(none)"
    return "\n".join(f"- {fact}" for fact in stored_facts)


async def judge_faithfulness(
    question: str,
    stored_facts: list[str],
    answer: str,
) -> FaithfulnessVerdict:
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Stored facts:\n{_format_facts(stored_facts)}\n\n"
        f"Assistant's answer:\n{answer}"
    )
    result = await faithfulness_agent.run(user_prompt)
    return result.output


async def judge_correctness(
    question: str,
    reference_answer: str,
    expect_abstention: bool,
    answer: str,
) -> CorrectnessVerdict:
    expected_behaviour = "ABSTAIN" if expect_abstention else "ANSWER"
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Expected behaviour: {expected_behaviour}\n\n"
        f"Reference answer:\n{reference_answer}\n\n"
        f"Assistant's answer:\n{answer}"
    )
    result = await correctness_agent.run(user_prompt)
    return result.output
