"""Predicted vs measured table (make perfmodel). Writes results/perfmodel_validation.csv."""
from __future__ import annotations

import csv

from perfmodel.model import HW, Params, fit, load_measurements, predict, size_of


def main() -> None:
    hw, ms = HW.load(), load_measurements()
    before, after = Params(), fit(HW.load(), ms)
    print(f"HW: triad {hw.triad_gbps} GB/s (1 thread), GEMM {hw.gemm_gflops} GFLOP/s, "
          f"{hw.cores} cores")
    print(f"fitted on 0.5B only: alpha_c={after.alpha_c:.2f} alpha_b={after.alpha_b:.2f} "
          f"eff_c={ {k: round(v, 2) for k, v in after.eff_c.items()} } "
          f"eff_b={ {k: round(v, 2) for k, v in after.eff_b.items()} }")
    rows = []
    hdr = "model                         thr  split     pp meas  pp before(err)  pp after(err)   " \
          "tg meas  tg before(err)  tg after(err)"
    print(hdr)
    for m in sorted(ms, key=lambda m: (m["name"], m["threads"])):
        b = predict(hw, before, m["name"], m["bytes"], m["threads"])
        a = predict(hw, after, m["name"], m["bytes"], m["threads"])
        split = "held-out(1.5B)" if size_of(m["name"]) == "1.5b" else (
            "fit(t=2)" if m["threads"] == 2 else "in-sample alpha")
        e = lambda pred, meas: 100 * (pred - meas) / meas  # noqa: E731
        r = {"model": m["name"], "threads": m["threads"], "split": split,
             "pp_meas": m["pp"], "pp_before": b[0], "pp_after": a[0],
             "pp_err_before_pct": e(b[0], m["pp"]), "pp_err_after_pct": e(a[0], m["pp"]),
             "tg_meas": m["tg"], "tg_before": b[1], "tg_after": a[1],
             "tg_err_before_pct": e(b[1], m["tg"]), "tg_err_after_pct": e(a[1], m["tg"])}
        rows.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
        print(f"{m['name'][:28]:28} {m['threads']:>3}  {split:15} {m['pp']:7.1f} "
              f"{b[0]:8.1f}({r['pp_err_before_pct']:+5.0f}%) "
              f"{a[0]:8.1f}({r['pp_err_after_pct']:+5.0f}%) "
              f"{m['tg']:7.1f} {b[1]:8.1f}({r['tg_err_before_pct']:+5.0f}%) "
              f"{a[1]:8.1f}({r['tg_err_after_pct']:+5.0f}%)")
    with open("results/perfmodel_validation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    held = [r for r in rows if r["split"].startswith("held")]
    mae = lambda k: sum(abs(r[k]) for r in held) / len(held)  # noqa: E731
    print(f"held-out 1.5B mean |err|: pp before {mae('pp_err_before_pct'):.0f}% after "
          f"{mae('pp_err_after_pct'):.0f}%; tg before {mae('tg_err_before_pct'):.0f}% after "
          f"{mae('tg_err_after_pct'):.0f}%")


if __name__ == "__main__":
    main()
