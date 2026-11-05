"""Planner vs measured operating points (2 replicas, 0.5B Q4_K_M, 2 threads/replica, baseline sweep)."""
from __future__ import annotations

import csv

from perfmodel.planner import PAR_PER_REPLICA, load_len_dists, rates, simulate


def main() -> None:
    pp, tg = rates("0.5b", "q4_k_m", 2)
    pre, out = load_len_dists()
    svc = float((pre / pp + out / tg).mean())
    cap = round(2 * PAR_PER_REPLICA) / svc
    print(f"service model: pp={pp:.1f} tok/s tg={tg:.1f} tok/s mean service {svc:.2f}s; "
          f"predicted capacity {cap:.2f} req/s (measured overload throughput 1.6-1.7)")
    print("measured arrival rps | measured p50/p95 TTFT | predicted p50/p95 | p95 error")
    for r in csv.DictReader(open("results/baseline_sweep.csv")):
        if float(r["offered_rps"]) not in (0.5, 1.0, 2.0):
            continue
        lam = float(r["arrival_rps"])
        s = simulate(lam, 2, pp, tg, pre, out)
        err = 100 * (s["ttft_p95"] - float(r["ttft_p95"])) / float(r["ttft_p95"])
        print(f"{lam:5.2f} | {float(r['ttft_p50']):.2f}/{float(r['ttft_p95']):.2f} s | "
              f"{s['ttft_p50']:.2f}/{s['ttft_p95']:.2f} s | {err:+.0f}%")


if __name__ == "__main__":
    main()
