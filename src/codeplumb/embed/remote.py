"""Opt-in remote embedders. Constructing one means chunk text leaves the machine."""

from __future__ import annotations

import os
import sys

import httpx

from codeplumb.embed.base import l2_normalize


def _warn(provider: str) -> None:
    print(f"[codeplumb] WARNING: sending chunk text to {provider} for embedding", file=sys.stderr)


class VoyageEmbedder:
    provider = "voyage"

    def __init__(self, model: str = "voyage-law-2") -> None:
        self.model = model
        self.name = f"voyage:{model}"
        self.dimensions = 1024
        self.doc_prefix = ""
        self.query_prefix = ""
        self._key = os.environ.get("VOYAGE_API_KEY") or _missing("VOYAGE_API_KEY")
        _warn("Voyage AI")

    def _call(self, texts: list[str], input_type: str) -> list[list[float]]:
        r = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"input": texts, "model": self.model, "input_type": input_type},
            timeout=60,
        )
        r.raise_for_status()
        return [l2_normalize(d["embedding"]) for d in r.json()["data"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            out.extend(self._call(texts[i : i + 64], "document"))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], "query")[0]


class OpenAIEmbedder:
    provider = "openai"

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self.model = model
        self.name = f"openai:{model}"
        self.dimensions = 1536
        self.doc_prefix = ""
        self.query_prefix = ""
        self._key = os.environ.get("OPENAI_API_KEY") or _missing("OPENAI_API_KEY")
        _warn("OpenAI")

    def _call(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"input": texts, "model": self.model},
            timeout=60,
        )
        r.raise_for_status()
        return [l2_normalize(d["embedding"]) for d in r.json()["data"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            out.extend(self._call(texts[i : i + 128]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call([text])[0]


def _missing(var: str):
    raise RuntimeError(f"{var} is not set")
