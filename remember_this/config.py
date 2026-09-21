from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore", 
    )

    telegram_bot_token: SecretStr

    llm_base_url: str
    llm_api_key: SecretStr
    llm_model: str = Field(default="qwen3.6:35b")
    embedding_model: str = Field(default="bge-m3")
    judge_model: str = Field(default="gemma4:26b")
    generator_model: str = Field(default="llama3.1:8b")

    database_url: str

    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    prompt_version: str = Field(default="v1")

    # These are guesses and will be revisited after experimentation
    strict_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    relaxed_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    embedding_retrieval_limit: int = Field(default=20)

    rate_limit_per_user_per_hour: int = Field(default=30, gt=0)

    user_id_salt: SecretStr

    @model_validator(mode="after")
    def _check_invariants(self) -> "Settings":
        if self.relaxed_threshold >= self.strict_threshold:
            raise ValueError("Relaxed Threshold must be lesser than strict threshold")
        if self.llm_model == self.judge_model:
            raise ValueError("LLM model must be different from judge model")
        if self.llm_model == self.generator_model:
            raise ValueError("LLM model must be different from generator model")
        return self

    @property
    def trace(self) -> dict:
        return {
            "llm.model": self.llm_model,
            "embedding.model": self.embedding_model,
            "prompt_version": self.prompt_version,
            "retrieval.strict_threshold": self.strict_threshold,
            "retrieval.relaxed_threshold": self.relaxed_threshold
        }

@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings, constructed once and cached."""
    settings = Settings()
    return settings