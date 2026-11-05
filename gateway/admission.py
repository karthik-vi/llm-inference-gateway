"""SLO-aware admission control: estimate TTFT from live load; reject early when it would miss."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class Decision:
    admit: bool
    est_ttft_s: float
    retry_after_s: int = 0


class AdmissionController:
    """est_ttft(replica) = ttft_base + queue_depth * service_time / slots,
    where queue_depth = requests in flight beyond the replica's free slots.
    ttft_base and service_time are EWMAs of observed values (ttft_base only from
    requests that started while a slot was free)."""

    def __init__(self, slo_ttft_s: float, slots: int, margin: float = 1.0,
                 init_ttft_s: float = 0.7, init_service_s: float = 2.0, alpha: float = 0.2) -> None:
        self.slo = slo_ttft_s
        self.slots = slots
        self.margin = margin
        self.ttft_base = init_ttft_s
        self.service = init_service_s
        self.alpha = alpha
        self.rejected = 0

    def observe(self, ttft_s: float | None, e2e_s: float, inflight_at_start: int) -> None:
        a = self.alpha
        self.service = (1 - a) * self.service + a * e2e_s
        if ttft_s is not None and inflight_at_start < self.slots:
            self.ttft_base = (1 - a) * self.ttft_base + a * ttft_s

    def estimate(self, inflight_on_replica: int) -> float:
        queue = max(0, inflight_on_replica - self.slots + 1)  # +1: this request
        return self.ttft_base + queue * self.service / self.slots

    def decide(self, inflight: Mapping[str, int]) -> Decision:
        """Best case over replicas (the router will send to the least loaded when admitting)."""
        est = self.estimate(min(inflight.values()))
        if est <= self.slo * self.margin:
            return Decision(True, est)
        self.rejected += 1
        return Decision(False, est, max(1, round(est - self.slo)))
