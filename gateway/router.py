"""Replica selection. Phase 1: round robin. Phase 2 adds prefix-aware routing."""
from __future__ import annotations

import itertools
import threading

from gateway.config import Replica


class RoundRobinRouter:
    def __init__(self, replicas: list[Replica]) -> None:
        if not replicas:
            raise ValueError("no replicas configured")
        self._replicas = replicas
        self._cycle = itertools.cycle(range(len(replicas)))
        self._lock = threading.Lock()

    def pick(self) -> Replica:
        with self._lock:
            return self._replicas[next(self._cycle)]
