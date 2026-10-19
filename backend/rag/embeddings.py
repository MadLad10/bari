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


class GeminiEmbedder(Embedder):
    """Google's gemini-embedding-001 via REST: the production embedder on Vercel, where bge-m3 can't run.

    Multilingual (100+ languages). Output is truncated to EMBEDDING_DIM (Matryoshka), so the `documents`
    schema is unchanged. Documents and queries use different task types, as the model expects."""

    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"

    def __init__(self, batch_size: int = 50, max_retries: int = 4, transport=None, sleep=time.sleep):
        import httpx
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set", retryable=False)
        self.api_model = settings.gemini_embedding_model
        self.model = f"{self.api_model}@{self.dim}"  # stored per document: a model change triggers re-embedding
        self.batch_size, self.max_retries, self._sleep = batch_size, max_retries, sleep
        self._http = httpx.Client(timeout=30, transport=transport)

    def _call(self, texts: list[str], task_type: str) -> list[list[float]]:
        import httpx
        body = {"requests": [{"model": f"models/{self.api_model}", "content": {"parts": [{"text": t[:8000]}]},
                              "taskType": task_type, "outputDimensionality": self.dim} for t in texts]}
        started, attempt = time.perf_counter(), 0
        while True:
            try:
                r = self._http.post(self.URL.format(model=self.api_model), json=body,
                                    headers={"x-goog-api-key": settings.gemini_api_key})
                if r.status_code == 429 or r.status_code >= 500:
                    retry_after = float(r.headers.get("retry-after", 0) or 0) or None
                    raise LLMError(f"gemini HTTP {r.status_code}", retryable=True, retry_after=retry_after,
                                   status=r.status_code)
                if r.status_code >= 400:
                    raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}", status=r.status_code)
                vectors = [e["values"] for e in r.json()["embeddings"]]
                break
            except httpx.TransportError as e:
                err = LLMError(f"gemini unreachable: {e}", retryable=True)
            except LLMError as e:
                err = e
            if not err.retryable or attempt >= self.max_retries:
                record_call(request_id=request_id_var.get() or "embed", provider="gemini", model=self.api_model,
                            purpose="embed", latency_ms=int((time.perf_counter() - started) * 1000),
                            status="error", error=str(err)[:1000], attempts=attempt + 1)
                raise err
            self._sleep(backoff_delay(attempt, err, 1.0, 20))
            attempt += 1
        tokens = sum(len(t) for t in texts) // 4  # the batch API doesn't report usage; estimate for the cost log
        record_call(request_id=request_id_var.get() or "embed", provider="gemini", model=self.api_model,
                    purpose="embed", prompt_tokens=tokens, completion_tokens=0,
                    cost_usd=round(tokens * 0.15 / 1_000_000, 8), status="ok", attempts=attempt + 1,
                    latency_ms=int((time.perf_counter() - started) * 1000))
        return vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out += self._call(texts[i:i + self.batch_size], "RETRIEVAL_DOCUMENT")
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], "RETRIEVAL_QUERY")[0]


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
    return {"ollama": OllamaEmbedder, "gemini": GeminiEmbedder, "fake": FakeEmbedder}[kind]()


def get_embedder() -> Embedder:
    return _override or _build(settings.embedding_provider)
