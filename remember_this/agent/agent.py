from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from remember_this.agent.prompt import driver_prompt
from remember_this.config import get_settings

_settings = get_settings()

_provider = OpenAIProvider(
    base_url=_settings.llm_base_url,
    api_key=_settings.llm_api_key.get_secret_value(),
)


class TurnResult(BaseModel):
    intent: Literal["feed", "question"]
    message_to_user: str
    cited_memory_ids: list[int] = []


class UserIdentifier:
    """Dependency injected into the agent run via RunContext.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

    def get_user_id(self) -> int:
        return self.user_id


agent = Agent(
    model=OpenAIChatModel(_settings.llm_model, provider=_provider),
    deps_type=UserIdentifier,
    output_type=str,
    system_prompt=driver_prompt,
    model_settings=ModelSettings(temperature=0.0),
)

# Imported for its side effect: registers save_memories / search_memories on
# `agent` via the @agent.tool decorator. Must come after `agent` is defined
# above, or tools.py's `from remember_this.agent.agent import agent` would
# import a module that hasn't finished defining it yet.
from remember_this.agent import tools


