"""Embedding models. Default: bge-m3 served by Ollama (multilingual, 1024-d, strong on Bangla)."""
from __future__ import annotations

import hashlib
import math
import re
import time
from abc import ABC, abstractmethod
from functools import lru_cache

from config import settings
from llm.base import LLMError
from llm.client import backoff_delay, record_call
from llm.context import request_id_var
from models import EMBEDDING_DIM


class Embedder(ABC):
    model: str
    dim: int = EMBEDDING_DIM

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OllamaEmbedder(Embedder):
    def __init__(self, batch_size: int = 16, max_retries: int = 3):
        from llm.ollama import OllamaProvider
        self.model = settings.embedding_model
        self._provider = OllamaProvider(settings.ollama_base_url, settings.embedding_model)
        self.batch_size, self.max_retries = batch_size, max_retries

    def _batch(self, texts: list[str]) -> list[list[float]]:
        started, attempt = time.perf_counter(), 0
        while True:
            try:
                vectors, tokens = self._provider.embed(texts, self.model)
                break
            except LLMError as e:
                if not e.retryable or attempt >= self.max_retries:
                    record_call(request_id=request_id_var.get() or "embed", provider="ollama", model=self.model,
                                purpose="embed", latency_ms=int((time.perf_counter() - started) * 1000),
                                status="error", error=str(e)[:1000], attempts=attempt + 1)
                    raise
                time.sleep(backoff_delay(attempt, e, 0.5, 8))
                attempt += 1
        record_call(request_id=request_id_var.get() or "embed", provider="ollama", model=self.model, purpose="embed",
                    prompt_tokens=tokens, completion_tokens=0, cost_usd=0.0, status="ok", attempts=attempt + 1,
                    latency_ms=int((time.perf_counter() - started) * 1000))
        return vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out += self._batch(texts[i:i + self.batch_size])
        return out


_TOKEN = re.compile(r"[\wঀ-৿]+", re.UNICODE)


class FakeEmbedder(Embedder):
    """Deterministic hashed bag-of-words + prefixes. No model, no network: for tests only.

    Texts that share words get similar vectors, which is enough to test the retrieval plumbing.
    """
    model = "fake-hash-embedder"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in _TOKEN.findall(text.lower()):
                for feat in {tok, tok[:5]}:
                    h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
                    vec[h % self.dim] += 1.0 if (h >> 20) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


_override: Embedder | None = None


def set_embedder_override(embedder: Embedder | None) -> None:
    global _override
    _override = embedder


@lru_cache
def _build(kind: str) -> Embedder:
    return {"ollama": OllamaEmbedder, "fake": FakeEmbedder}[kind]()


def get_embedder() -> Embedder:
    return _override or _build(settings.embedding_provider)
