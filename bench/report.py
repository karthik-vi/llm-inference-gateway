"""Summarise a sweep (SLO applied here) -> results/<tag>_sweep.csv + plot."""
from __future__ import annotations

import argparse
import csv
import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from workloads.loadgen import Rec, summarize  # noqa: E402


def read(path: str) -> list[Rec]:
    out = []
    for r in csv.DictReader(open(path)):
        out.append(Rec(int(r["session"]), int(r["turn"]), float(r["t_start"]), float(r["ttft"]),
                       float(r["itl_mean"]), float(r["e2e"]), int(r["prompt_tokens"]),
                       int(r["completion_tokens"]), r["status"], r["replica"],
                       int(r.get("prefill_tokens") or 0), int(r.get("cached_tokens") or 0)))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--slo", type=float, required=True)
    ap.add_argument("--duration", type=float, default=60)
    a = ap.parse_args()
    files = sorted(glob.glob(f"results/raw/{a.tag}_*.csv"),
                   key=lambda p: float(p.rsplit("_", 1)[1][:-4]))
    rows = []
    for f in files:
        s = summarize(read(f), a.duration, a.slo)
        s["offered_rps"] = float(f.rsplit("_", 1)[1][:-4])
        rows.append(s)
    keys = ["offered_rps"] + [k for k in rows[0] if k != "offered_rps"]
    with open(f"results/{a.tag}_sweep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    x = [r["offered_rps"] for r in rows]
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for k in ("ttft_p50", "ttft_p95", "ttft_p99"):
        ax[0].plot(x, [r[k] for r in rows], marker="o", label=k)
    ax[0].axhline(a.slo, ls="--", c="gray", label=f"SLO {a.slo}s")
    ax[0].set_yscale("log")
    ax[0].set_xlabel("offered req/s")
    ax[0].set_ylabel("TTFT (s)")
    ax[0].legend()
    ax[1].plot(x, [r["throughput_rps"] for r in rows], marker="o", label="throughput")
    ax[1].plot(x, [r["goodput_rps"] for r in rows], marker="o", label="goodput")
    ax[1].set_xlabel("offered req/s")
    ax[1].set_ylabel("req/s")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(f"results/plots/{a.tag}_sweep.png", dpi=80)
    for r in rows:
        print({k: round(v, 3) for k, v in r.items()})
