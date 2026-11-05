import numpy as np

from gateway.semcache import SemanticCache, cacheable


def _fake_embed(texts: list[str]) -> np.ndarray:
    # deterministic 8-d vectors: texts sharing the first word are near-identical
    out = []
    for t in texts:
        v = np.zeros(8, dtype="float32")
        v[hash(t.split()[0]) % 8] = 1.0
        v[7] += 0.01 * len(t)
        out.append(v / np.linalg.norm(v))
    return np.vstack(out)


def test_cacheable_rules() -> None:
    u = lambda c: {"role": "user", "content": c}  # noqa: E731
    s = {"role": "system", "content": "x"}
    assert cacheable([s, u("how do I reset my password")])
    assert not cacheable([s, u("cancel order 12345")])
    assert not cacheable([s, u("where is my order")])
    assert not cacheable([s, u("hi"), {"role": "assistant", "content": "a"}, u("and then?")])


def test_hit_miss_threshold() -> None:
    c = SemanticCache(_fake_embed, threshold=0.99, dim=8)
    assert c.lookup("hello world")[0] is None  # empty
    c.add("hello world", "ANSWER")
    assert c.lookup("hello world")[0] == "ANSWER"
    assert c.lookup("zebra crossing")[0] is None
    assert c.hits == 1 and c.lookups == 3
