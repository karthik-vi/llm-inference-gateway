"""Replica selection: round robin, or prefix-aware consistent hashing with load fallback."""
from __future__ import annotations

import bisect
import hashlib
import itertools
import threading
from collections.abc import Mapping

from gateway.config import Replica


class RoundRobinRouter:
    def __init__(self, replicas: list[Replica]) -> None:
        if not replicas:
            raise ValueError("no replicas configured")
        self._replicas = replicas
        self._cycle = itertools.cycle(range(len(replicas)))
        self._lock = threading.Lock()

    def pick(self, key: str | None = None, inflight: Mapping[str, int] | None = None) -> Replica:
        with self._lock:
            return self._replicas[next(self._cycle)]


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


class PrefixRouter:
    """Consistent hash ring on a prefix key; falls back to least-loaded when the preferred
    replica has >= max_inflight requests in flight (so a hot prefix cannot starve a replica)."""

    def __init__(self, replicas: list[Replica], max_inflight: int = 6, vnodes: int = 64) -> None:
        if not replicas:
            raise ValueError("no replicas configured")
        self._replicas = {r.name: r for r in replicas}
        self._max = max_inflight
        ring = sorted((_h(f"{r.name}#{v}"), r.name) for r in replicas for v in range(vnodes))
        self._points = [p for p, _ in ring]
        self._names = [n for _, n in ring]
        self.fallbacks = 0

    def preferred(self, key: str) -> str:
        i = bisect.bisect(self._points, _h(key)) % len(self._points)
        return self._names[i]

    def pick(self, key: str | None = None, inflight: Mapping[str, int] | None = None) -> Replica:
        load = inflight or {}
        name = self.preferred(key or "")
        if load.get(name, 0) >= self._max:
            alt = min(self._replicas, key=lambda n: load.get(n, 0))
            if alt != name:
                self.fallbacks += 1
                name = alt
        return self._replicas[name]


def prefix_key(messages: list[dict]) -> str:
    """Stable across the turns of a session: system prompt + first user message."""
    first_user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    return f"{system}\x00{first_user}"


def make_router(kind: str, replicas: list[Replica], max_inflight: int):
    if kind == "prefix":
        return PrefixRouter(replicas, max_inflight=max_inflight)
    if kind == "round_robin":
        return RoundRobinRouter(replicas)
    raise ValueError(f"unknown routing: {kind}")
