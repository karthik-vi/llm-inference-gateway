"""Tune the semantic-cache threshold. Ground truth = Bitext intent label of the nearest cached
query vs the incoming query (a PROXY for 'same answer is acceptable').
Output: results/semcache_tuning.csv + results/plots/semcache_tuning.png."""
from __future__ import annotations

import csv
import random

import faiss
import matplotlib
import numpy as np

from gateway.semcache import cacheable, fastembed_fn, normalize

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

N_INDEX, N_QUERY, SEED = 8000, 3000, 0

if __name__ == "__main__":
    rows = list(csv.DictReader(open("data/bitext.csv", encoding="utf-8")))
    rows = [r for r in rows if cacheable([{"role": "user", "content": r["instruction"]}])]
    rng = random.Random(SEED)
    rng.shuffle(rows)
    idx_rows, q_rows = rows[:N_INDEX], rows[N_INDEX:N_INDEX + N_QUERY]
    emb = fastembed_fn()
    E = lambda rs: np.vstack([emb([normalize(r["instruction"]) for r in rs[i:i + 256]])  # noqa: E731
                              for i in range(0, len(rs), 256)])
    X, Q = E(idx_rows), E(q_rows)
    ix = faiss.IndexFlatIP(X.shape[1]); ix.add(X)
    sims, nn = ix.search(Q, 1)
    ok = np.array([idx_rows[j[0]]["intent"] == q["intent"] for j, q in zip(nn, q_rows)])
    out = []
    for t in np.arange(0.80, 1.0001, 0.01):
        hit = sims[:, 0] >= t
        n = int(hit.sum())
        out.append({"threshold": round(float(t), 2), "hit_rate": n / len(q_rows),
                    "wrong_rate_of_hits": float((~ok[hit]).sum() / n) if n else 0.0,
                    "wrong_per_query": float((~ok[hit]).sum() / len(q_rows))})
    with open("results/semcache_tuning.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    th = [o["threshold"] for o in out]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(th, [o["hit_rate"] for o in out], label="hit rate")
    ax.plot(th, [o["wrong_rate_of_hits"] for o in out], label="wrong-answer rate (of hits)")
    ax.set_xlabel("similarity threshold"); ax.legend(); fig.tight_layout()
    fig.savefig("results/plots/semcache_tuning.png", dpi=80)
    print(f"index={len(idx_rows)} queries={len(q_rows)} (cacheable Bitext rows only)")
    for o in out[::2]:
        print({k: round(v, 4) for k, v in o.items()})
