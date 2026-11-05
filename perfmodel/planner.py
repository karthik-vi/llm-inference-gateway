"""Capacity planner: replicas needed for a workload to meet a p95-TTFT SLO.

Service-time model (perfmodel.model, v2) -> per-request prefill/decode time; Monte Carlo
FIFO queue with `c = replicas * par_per_replica` servers on top (M/G/c with empirical length
distributions). `par_per_replica` is the effective parallelism of one replica (continuous
batching on few threads gives far less than `--parallel` slots); calibrated from the measured
baseline saturation throughput, see docs/DECISIONS.md ADR-010.

Usage: python -m perfmodel.planner --rate 1.5 --slo 2.0 [--model 0.5b --quant q4_k_m ...]
"""
from __future__ import annotations

import argparse
import csv
import glob
import heapq
import random

import numpy as np

from perfmodel.model import HW, fit, load_measurements, predict

PAR_PER_REPLICA = 1.55   # calibrated: ADR-010 (measured saturation 1.7 req/s on 2 replicas)
OVERHEAD_S = 0.0         # per-request overhead (gateway+HTTP); measured in ADR-010


def load_len_dists() -> tuple[np.ndarray, np.ndarray]:
    """Empirical (recomputed-prefill tokens, output tokens) from recorded round-robin runs."""
    pre, out = [], []
    for f in glob.glob("results/raw/rr_*.csv"):
        for r in csv.DictReader(open(f)):
            if r["status"] == "ok" and int(r["completion_tokens"]) > 0:
                pre.append(int(r["prefill_tokens"]))
                out.append(int(r["completion_tokens"]))
    return np.array(pre), np.array(out)


def rates(model: str, quant: str, threads: int) -> tuple[float, float]:
    ms = load_measurements()
    name = f"qwen2.5-{model}-instruct-{quant}"
    size = next((m["bytes"] for m in ms if m["name"] == name), None)
    if size is None:
        raise SystemExit(f"no measured file size for {name} (run bench/quant.sh)")
    return predict(HW.load(), fit(HW.load(), ms), name, size, threads)


def simulate(rate: float, replicas: int, pp: float, tg: float, pre: np.ndarray, out: np.ndarray,
             par: float = PAR_PER_REPLICA, n: int = 20000, seed: int = 0) -> dict:
    """FIFO M/G/c; returns TTFT percentiles. TTFT = queue wait + prefill time."""
    rng = random.Random(seed)
    c = max(1, round(replicas * par))
    free = [0.0] * c
    heapq.heapify(free)
    t, ttfts = 0.0, []
    for _ in range(n):
        t += rng.expovariate(rate)
        i = rng.randrange(len(pre))
        t_pre = pre[i] / pp + OVERHEAD_S
        t_svc = t_pre + out[i] / tg
        start = max(t, heapq.heappop(free))
        heapq.heappush(free, start + t_svc)
        ttfts.append(start - t + t_pre)
    a = np.array(ttfts[n // 10:])  # drop warm-up
    return {"servers": c, "ttft_p50": float(np.percentile(a, 50)),
            "ttft_p95": float(np.percentile(a, 95)), "ttft_p99": float(np.percentile(a, 99))}


def plan(rate: float, slo: float, model: str, quant: str, threads: int, max_replicas: int = 16,
         pre: np.ndarray | None = None, out: np.ndarray | None = None) -> list[dict]:
    pp, tg = rates(model, quant, threads)
    if pre is None or out is None:
        pre, out = load_len_dists()
    rows = []
    for r in range(1, max_replicas + 1):
        s = simulate(rate, r, pp, tg, pre, out)
        s.update(replicas=r, meets_slo=s["ttft_p95"] <= slo)
        rows.append(s)
        if s["meets_slo"]:
            break
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, required=True, help="request arrival rate (req/s)")
    ap.add_argument("--slo", type=float, default=2.0, help="p95 TTFT target (s)")
    ap.add_argument("--model", default="0.5b")
    ap.add_argument("--quant", default="q4_k_m")
    ap.add_argument("--threads", type=int, default=2, help="threads per replica")
    ap.add_argument("--max-replicas", type=int, default=16)
    a = ap.parse_args()
    rows = plan(a.rate, a.slo, a.model, a.quant, a.threads, a.max_replicas)
    for r in rows:
        print(f"replicas={r['replicas']:>2} (servers={r['servers']}) p95_ttft={r['ttft_p95']:.2f}s "
              f"p50={r['ttft_p50']:.2f}s {'OK' if r['meets_slo'] else 'misses SLO'}")
    last = rows[-1]
    print(("RECOMMEND" if last["meets_slo"] else "NOT ACHIEVED") +
          f": {last['replicas']} replicas x {a.threads} threads "
          f"({last['replicas'] * a.threads} cores) for {a.rate} req/s, p95 TTFT <= {a.slo}s; "
          f"predicted p95 {last['ttft_p95']:.2f}s")
