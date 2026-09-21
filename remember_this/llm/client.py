from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from remember_this.config import Settings, get_settings

_settings = get_settings()

_provider = OpenAIProvider(
    base_url=_settings.llm_base_url,
    api_key=_settings.llm_api_key.get_secret_value(),
)


def create_agent(
    model_key: str,
    output_type: type,
    system_prompt: str,
    temperature: float
) -> Agent:
    """Build a Pydantic AI agent for one of the configured model roles.

    model_key: an attribute name on Settings, e.g. "llm_model", "judge_model",
    "generator_model" -- not the model id itself.
    """
    model_name = getattr(_settings, model_key)
    model = OpenAIChatModel(model_name, provider=_provider)

    return Agent(
        model=model,
        output_type=output_type,
        system_prompt=system_prompt,
        model_settings=ModelSettings(temperature=temperature)
    )