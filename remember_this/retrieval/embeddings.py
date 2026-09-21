from openai import AsyncOpenAI

from remember_this.config import get_settings

Settings = get_settings()

_client = AsyncOpenAI(
    base_url=Settings.llm_base_url,
    api_key=Settings.llm_api_key.get_secret_value()
)

async def embed_text(text_to_embed: list[str]) -> list[list[float]]:
    embeddings = await _client.embeddings.create(
        input=text_to_embed,
        model=Settings.embedding_model
    )
    return [e.embedding for e in embeddings.data]
