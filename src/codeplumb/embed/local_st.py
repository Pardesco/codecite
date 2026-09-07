from __future__ import annotations

from codeplumb.embed.base import l2_normalize

_PREFIXES = {
    "nomic-ai/nomic-embed-text-v1.5": ("search_document: ", "search_query: "),
    "nomic-ai/nomic-embed-text-v1": ("search_document: ", "search_query: "),
}


class LocalSentenceTransformers:
    """Default, zero-cost embedder. Runs on CUDA when available, else CPU."""

    provider = "local-st"

    def __init__(self, model: str = "nomic-ai/nomic-embed-text-v1.5", device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers not installed; run `uv sync --extra local` "
                "or set CODEPLUMB_EMBED_PROVIDER=fake for tests"
            ) from e
        self.model = model
        self.name = f"local-st:{model}"
        self.doc_prefix, self.query_prefix = _PREFIXES.get(model, ("", ""))
        self._m = SentenceTransformer(model, trust_remote_code=True, device=device)
        self.dimensions = int(self._m.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out = self._m.encode([self.doc_prefix + t for t in texts], batch_size=32, normalize_embeddings=True)
        return [l2_normalize(v.tolist()) for v in out]

    def embed_query(self, text: str) -> list[float]:
        v = self._m.encode(self.query_prefix + text, normalize_embeddings=True)
        return l2_normalize(v.tolist())
