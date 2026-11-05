import pytest

from gateway.config import Replica
from gateway.router import RoundRobinRouter


def test_round_robin_cycles_evenly() -> None:
    reps = [Replica(name=f"r{i}", url=f"http://x:{i}") for i in range(3)]
    r = RoundRobinRouter(reps)
    picks = [r.pick().name for _ in range(9)]
    assert picks == ["r0", "r1", "r2"] * 3


def test_empty_replicas_rejected() -> None:
    with pytest.raises(ValueError):
        RoundRobinRouter([])
