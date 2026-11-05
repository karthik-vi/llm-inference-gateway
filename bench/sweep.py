"""Rate sweep against a running gateway. Raw per-request CSVs -> results/raw/<tag>_<rate>.csv."""
from __future__ import annotations

import argparse
import asyncio

from workloads.loadgen import run, write_csv
from workloads.trace import load

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--rates", default="0.5,1,2,3,4,6")
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--think", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--trace", default="data/trace.jsonl")
    a = ap.parse_args()
    sessions = load(a.trace)
    for rate in [float(x) for x in a.rates.split(",")]:
        recs = asyncio.run(run(a.url, sessions, rate, a.duration, a.think, a.timeout, seed=1))
        write_csv(recs, f"results/raw/{a.tag}_{rate}.csv")
        print(f"rate={rate} n={len(recs)}", flush=True)
