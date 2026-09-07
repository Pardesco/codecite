from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class Embedder(Protocol):
    name: str
    provider: str
    model: str
    dimensions: int
    doc_prefix: str
    query_prefix: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def l2_normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


_TOKEN = re.compile(r"[a-z0-9]+")


class FakeEmbedder:
    """Deterministic hashed bag-of-words embedder for tests and CI. No model download.

    Shared vocabulary between query and document lands in the same buckets, so
    similarity is roughly lexical overlap. Good enough to exercise the pipeline.
    """

    provider = "fake"
    abstain_similarity = 0.30  # hashed-BoW cosine runs low; real models use Settings.abstain_similarity

    def __init__(self, dimensions: int = 768, model: str = "hashed-bow") -> None:
        self.model = model
        self.dimensions = dimensions
        self.name = f"fake:{model}"
        self.doc_prefix = ""
        self.query_prefix = ""

    def _embed(self, text: str) -> list[float]:
        v = [0.0] * self.dimensions
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.blake2b(tok.encode(), digest_size=8).hexdigest(), 16)
            v[h % self.dimensions] += 1.0
            v[(h >> 16) % self.dimensions] += 0.5
        if not any(v):
            v[0] = 1.0
        return l2_normalize(v)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
