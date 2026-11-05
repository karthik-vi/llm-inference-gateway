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


def test_prefix_router_sticky_and_balanced() -> None:
    from gateway.router import PrefixRouter, prefix_key

    reps = [Replica(name=f"r{i}", url=f"http://x:{i}") for i in range(2)]
    r = PrefixRouter(reps)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "q1"}]
    k = prefix_key(msgs)
    assert len({r.pick(k).name for _ in range(20)}) == 1
    longer = msgs + [{"role": "assistant", "content": "a"}, {"role": "user", "content": "q2"}]
    assert prefix_key(longer) == k  # same key across turns of a session
    counts = {"r0": 0, "r1": 0}
    for i in range(1000):
        counts[r.pick(f"key{i}").name] += 1
    assert min(counts.values()) > 300


def test_prefix_router_falls_back_when_saturated() -> None:
    from gateway.router import PrefixRouter

    reps = [Replica(name=f"r{i}", url=f"http://x:{i}") for i in range(2)]
    r = PrefixRouter(reps, max_inflight=3)
    pref = r.preferred("k")
    other = "r1" if pref == "r0" else "r0"
    assert r.pick("k", {pref: 3, other: 0}).name == other
    assert r.pick("k", {pref: 2, other: 0}).name == pref
    assert r.fallbacks == 1
