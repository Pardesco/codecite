from __future__ import annotations

from codeplumb.config import Settings, get_settings
from codeplumb.embed.base import Embedder, FakeEmbedder


def get_embedder(settings: Settings | None = None, *, provider: str | None = None, model: str | None = None) -> Embedder:
    s = settings or get_settings()
    provider = provider or s.embed_provider
    model = model or s.embed_model
    if provider == "fake":
        return FakeEmbedder(s.embed_dimensions)
    if provider == "local-st":
        from codeplumb.embed.local_st import LocalSentenceTransformers

        return LocalSentenceTransformers(model)
    if provider in ("voyage", "openai"):
        if not s.allow_remote_embeddings:
            raise RuntimeError(
                f"provider '{provider}' sends chunk text off-machine; "
                "set CODEPLUMB_ALLOW_REMOTE_EMBEDDINGS=1 to opt in"
            )
        from codeplumb.embed.remote import OpenAIEmbedder, VoyageEmbedder

        return VoyageEmbedder(model) if provider == "voyage" else OpenAIEmbedder(model)
    raise ValueError(f"unknown embedding provider '{provider}'")


__all__ = ["Embedder", "FakeEmbedder", "get_embedder"]
