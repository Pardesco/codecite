from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODECITE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://codecite:codecite@127.0.0.1:5432/codecite"
    embed_provider: str = "local-st"  # local-st | fake | voyage | openai
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embed_dimensions: int = 768
    allow_remote_embeddings: bool = False
    enable_ingest_tool: bool = False
    ingest_root: str = "./corpus"
    rrf_k: int = 60
    candidate_limit: int = 40
    # cosine floor for abstain (no strict FTS hit and nearest vector below this). Tuned for
    # nomic-embed-text-v1.5 on the synthetic golden set; re-tune per model with `codecite eval`.
    abstain_similarity: float = 0.66


def get_settings() -> Settings:
    return Settings()
