"""Cross-encoder reranking. Default: BAAI/bge-reranker-v2-m3 (multilingual, Apache-2.0), int8 ONNX via
fastembed, so the backend needs no PyTorch. It scores (query, passage) pairs jointly, which is far more
precise than comparing embeddings, so it only runs on the top fused candidates."""
from __future__ import annotations

import re
import threading
from abc import ABC, abstractmethod
from functools import lru_cache

from config import settings


class Reranker(ABC):
    name: str

    @abstractmethod
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class BGEReranker(Reranker):
    def __init__(self):
        self.name = settings.reranker_model
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                self._model = TextCrossEncoder(model_name=self.name, cache_dir=settings.reranker_cache_dir)
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        # Truncated: cross-encoder cost grows with length, and chunks are ≤ ~700 characters anyway.
        return [float(s) for s in self._load().rerank(query, [p[:800] for p in passages], batch_size=8)]


_WORD = re.compile(r"[\wঀ-৿]+")


class FakeReranker(Reranker):
    """Token-overlap scorer for tests."""
    name = "fake-overlap"

    def score(self, query: str, passages: list[str]) -> list[float]:
        q = set(_WORD.findall(query.lower()))
        return [len(q & set(_WORD.findall(p.lower()))) / (len(q) or 1) for p in passages]


_override: Reranker | None = None
_disabled = object()


def set_reranker_override(reranker: Reranker | None) -> None:
    global _override
    _override = reranker


@lru_cache
def _build(kind: str) -> Reranker | None:
    return {"bge": BGEReranker, "fake": FakeReranker}.get(kind, lambda: None)()


def get_reranker() -> Reranker | None:
    return _override if _override is not None else _build(settings.reranker)
