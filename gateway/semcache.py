"""Semantic cache: FAISS inner-product index over normalised bge-small embeddings."""
from __future__ import annotations

import re
import threading
from collections.abc import Callable, Sequence

import numpy as np

_STATE = re.compile(
    r"\d|\b(my order|my account|my refund|my invoice|my payment|my package|my delivery|"
    r"order number|tracking)\b", re.I)


def cacheable(messages: Sequence[dict]) -> bool:
    """Only single-turn, context-free FAQ-style messages: exactly one user message and no
    assistant history, and no digits / account-state wording (those depend on account state)."""
    users = [m for m in messages if m.get("role") == "user"]
    if len(users) != 1 or any(m.get("role") == "assistant" for m in messages):
        return False
    return not _STATE.search(users[0]["content"])


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def fastembed_fn(model: str = "BAAI/bge-small-en-v1.5") -> Callable[[list[str]], np.ndarray]:
    from fastembed import TextEmbedding

    m = TextEmbedding(model)

    def embed(texts: list[str]) -> np.ndarray:
        v = np.asarray(list(m.embed(texts)), dtype="float32")
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    return embed


class SemanticCache:
    def __init__(self, embed: Callable[[list[str]], np.ndarray], threshold: float,
                 dim: int = 384) -> None:
        import faiss

        self.embed, self.threshold = embed, threshold
        self.index = faiss.IndexFlatIP(dim)
        self.answers: list[str] = []
        self._lock = threading.Lock()
        self.hits = self.lookups = 0

    def lookup(self, text: str) -> tuple[str | None, float]:
        self.lookups += 1
        with self._lock:
            if not self.answers:
                return None, 0.0
            q = self.embed([normalize(text)])
            sim, idx = self.index.search(q, 1)
        s = float(sim[0][0])
        if s >= self.threshold:
            self.hits += 1
            return self.answers[int(idx[0][0])], s
        return None, s

    def add(self, text: str, answer: str) -> None:
        v = self.embed([normalize(text)])
        with self._lock:
            self.index.add(v)
            self.answers.append(answer)
