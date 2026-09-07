from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODEPLUMB_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://codeplumb:codeplumb@127.0.0.1:5432/codeplumb"
    embed_provider: str = "local-st"  # local-st | fake | voyage | openai
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embed_dimensions: int = 768
    allow_remote_embeddings: bool = False
    enable_ingest_tool: bool = False
    ingest_root: str = "./corpus"
    rrf_k: int = 60
    candidate_limit: int = 40
    abstain_similarity: float = 0.45  # cosine; below this with no strict FTS hit => abstain


def get_settings() -> Settings:
    return Settings()
