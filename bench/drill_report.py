"""Analyse a drill: per-window SLI, offline alert evaluation, trace root-cause, dashboard panels.
python -m bench.drill_report --tag nobreaker"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SLO_S, WIN = 2.0, 10.0
SHORT, LONG, BURN, BUDGET = 10.0, 30.0, 14.4, 0.01   # drill-scaled windows (prod: 5m / 1h)


def windows(rows: list[dict], end: float) -> list[dict]:
    out = []
    for w0 in np.arange(0, end, WIN):
        rs = [r for r in rows if w0 <= float(r["t_start"]) < w0 + WIN]
        ok = [r for r in rs if r["status"] == "ok" and float(r["ttft"]) >= 0]
        tt = [float(r["ttft"]) for r in ok]
        out.append({"t": float(w0), "n": len(rs), "err_rate": 1 - len(ok) / len(rs) if rs else 0.0,
                    "p95": float(np.percentile(tt, 95)) if tt else float("nan"),
                    "good_frac": sum(t <= SLO_S for t in tt) / len(rs) if rs else 1.0,
                    "r1_share": sum(r["replica"] == "r1" for r in rs) / len(rs) if rs else 0.0})
    return out


def series(metrics: list[dict]) -> dict[str, np.ndarray]:
    t = np.array([m["t"] for m in metrics])

    def total(prefix: str, must: str = "") -> np.ndarray:
        return np.array([sum(v for k, v in m["m"].items() if k.startswith(prefix) and must in k)
                         for m in metrics])
    return {"t": t, "req": total("gw_requests_total{"),
            "good": total("gw_ttft_seconds_bucket{", 'le="2.0"'),
            "errors": total("gw_errors_total{"), "goodput": total("gw_goodput_total"),
            "inflight_r0": total("gw_inflight{", 'replica="r0"'),
            "inflight_r1": total("gw_inflight{", 'replica="r1"')}


def burn_at(s: dict, i: int, span: float) -> float | None:
    j = np.searchsorted(s["t"], s["t"][i] - span)
    if j >= i:
        return None
    dreq, dgood = s["req"][i] - s["req"][j], s["good"][i] - s["good"][j]
    return (1 - dgood / dreq) / BUDGET if dreq > 0 else None


def alerts(s: dict, events: list[dict]) -> dict:
    fire_fast, fire_err = [], []
    for i in range(len(s["t"])):
        b_s, b_l = burn_at(s, i, SHORT), burn_at(s, i, LONG)
        if b_s is not None and b_l is not None and b_s > BURN and b_l > BURN:
            fire_fast.append(float(s["t"][i]))
        j = np.searchsorted(s["t"], s["t"][i] - SHORT)
        if j < i and s["errors"][i] - s["errors"][j] > 0:
            fire_err.append(float(s["t"][i]))
    return {"SLOFastBurn": fire_fast, "ReplicaErrors": fire_err}


def spans(path: Path, t0: float) -> list[dict]:
    out = []
    for ln in path.read_text().splitlines() if path.exists() else []:
        try:
            sp = json.loads(ln)
        except ValueError:
            continue
        if sp.get("name") != "upstream":
            continue
        t = datetime.fromisoformat(sp["start_time"].replace("Z", "+00:00")).timestamp() - t0
        out.append({"t": t, "replica": sp["attributes"].get("replica"),
                    "error": sp["status"]["status_code"] == "ERROR",
                    "ttft": sp["attributes"].get("ttft_s"),
                    "prefill_ms": sp["attributes"].get("llama.prompt_ms"),
                    "decode_ms": sp["attributes"].get("llama.decode_ms"),
                    "queue": sp["attributes"].get("queue_wait_est_s")})
    return out


def main(tag: str) -> None:
    d = Path(f"results/drill_{tag}")
    ev = json.load(open(d / "events.json"))
    tl, t0 = ev["timeline"], ev["t0_epoch"]
    rows = list(csv.DictReader(open(d / "load.csv")))
    metrics = [json.loads(ln) for ln in open(d / "metrics.jsonl")]
    ws, s = windows(rows, tl["end"]), series(metrics)
    sp = spans(d / "spans.jsonl", t0)
    phases = {"healthy_0_40": (0, tl["kill"]), "r1_killed": (tl["kill"], tl["restart"]),
              "healthy_80_120": (tl["restart"] + 5, tl["throttle"]),
              "r1_throttled": (tl["throttle"], tl["unthrottle"]),
              "after_170": (tl["unthrottle"], tl["end"])}
    summ: dict = {"tag": tag, "breaker": ev["breaker"], "phases": {}}
    for name, (a, b) in phases.items():
        rs = [r for r in rows if a <= float(r["t_start"]) < b]
        ok = [r for r in rs if r["status"] == "ok" and float(r["ttft"]) >= 0]
        tt = [float(r["ttft"]) for r in ok]
        summ["phases"][name] = {
            "n": len(rs), "error_rate": round(1 - len(ok) / len(rs), 3) if rs else None,
            "p95_ttft": round(float(np.percentile(tt, 95)), 2) if tt else None,
            "good_frac": round(sum(t <= SLO_S for t in tt) / len(rs), 3) if rs else None,
            "to_r1": round(sum(r["replica"] == "r1" for r in rs) / len(rs), 2) if rs else None}
    al = alerts(s, ev["events"])
    kill, thr = tl["kill"], tl["throttle"]
    first = lambda xs, lo, hi: next((x for x in xs if lo <= x < hi), None)  # noqa: E731
    summ["alerts"] = {
        "ReplicaErrors_first_fire_after_kill_s": (None if first(al["ReplicaErrors"], kill, tl["restart"])
                                                  is None else round(first(al["ReplicaErrors"], kill,
                                                                           tl["restart"]) - kill, 1)),
        "SLOFastBurn_first_fire_after_kill_s": (None if first(al["SLOFastBurn"], kill, tl["restart"])
                                                is None else round(first(al["SLOFastBurn"], kill,
                                                                         tl["restart"]) - kill, 1)),
        "SLOFastBurn_first_fire_after_throttle_s": (None if first(al["SLOFastBurn"], thr, tl["end"])
                                                    is None else round(first(al["SLOFastBurn"], thr,
                                                                             tl["end"]) - thr, 1)),
        "note": f"burn-rate rule evaluated offline on scraped counters, windows scaled to {SHORT:.0f}s/"
                f"{LONG:.0f}s (prod 5m/1h), threshold {BURN}x of a {BUDGET:.0%} budget"}
    kill_sp = [x for x in sp if kill <= x["t"] < tl["restart"]]
    err = [x for x in kill_sp if x["error"]]
    summ["traces"] = {"upstream_spans_in_kill_window": len(kill_sp), "error_spans": len(err),
                      "error_spans_by_replica": {r: sum(x["replica"] == r for x in err)
                                                 for r in sorted({x["replica"] for x in err})}}
    for rep in ("r0", "r1"):
        xs = [x for x in sp if thr + 5 <= x["t"] < tl["unthrottle"] and x["replica"] == rep and x["ttft"]]
        if xs:
            summ["traces"][f"throttle_window_{rep}"] = {
                "n": len(xs), "ttft_mean_s": round(float(np.mean([x["ttft"] for x in xs])), 2),
                "llama_prefill_ms_mean": round(float(np.mean([x["prefill_ms"] or 0 for x in xs])), 0),
                "llama_decode_ms_mean": round(float(np.mean([x["decode_ms"] or 0 for x in xs])), 0)}
    json.dump(summ, open(d / "summary.json", "w"), indent=1)
    # dashboard-equivalent panels (Grafana cannot run here)
    fig, ax = plt.subplots(2, 2, figsize=(11, 6.5), sharex=True)
    x = [w["t"] + WIN / 2 for w in ws]
    ax[0][0].plot(x, [w["p95"] for w in ws], marker="o"); ax[0][0].axhline(SLO_S, ls="--", c="gray")
    ax[0][0].set_title("p95 TTFT per 10 s (s); dashed = SLO")
    ax[0][1].plot(x, [w["err_rate"] for w in ws], marker="o", c="C3")
    ax[0][1].set_title("error/reject rate per 10 s")
    ax[1][0].plot(s["t"], s["inflight_r0"], label="r0"); ax[1][0].plot(s["t"], s["inflight_r1"], label="r1")
    ax[1][0].legend(); ax[1][0].set_title("in-flight per replica (gw_inflight)")
    ax[1][1].plot(x, [w["good_frac"] for w in ws], marker="o", c="C2")
    ax[1][1].set_title("fraction of requests good (TTFT<=2 s)")
    for a in ax.flat:
        for e in ev["events"]:
            a.axvline(e["t"], c="k", alpha=.25, lw=1)
        a.set_xlabel("s")
    fig.tight_layout(); fig.savefig(f"results/plots/drill_{tag}.png", dpi=70)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    main(ap.parse_args().tag)
