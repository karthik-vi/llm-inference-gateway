"""Analytical roofline model for llama.cpp on CPU.

prefill tokens/s  = eff_c[quant] * (gemm_gflops/cores) * t^alpha_c * 1e9 / (2 * params)
decode  tokens/s  = eff_b[quant] * triad_GBps * t^alpha_b * 1e9 / weight_bytes     (batch 1)
Decode reads all weights per token (memory-bound); prefill does 2*params FLOPs/token.
"before": eff = 1, alpha = 1 (raw microbenchmarks scaled linearly with threads).
"after" : alpha and per-quant eff fitted ONCE on Qwen2.5-0.5B only, then tested on 1.5B."""
from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field

PARAMS = {"0.5b": 494e6, "1.5b": 1.54e9}   # Qwen2.5 total parameter counts


def quant_of(name: str) -> str:
    return next(q for q in ("q4_k_m", "q8_0", "fp16") if q in name)


def size_of(name: str) -> str:
    return "0.5b" if "0.5b" in name else "1.5b"


@dataclass
class HW:
    triad_gbps: float
    gemm_gflops: float
    cores: int

    @classmethod
    def load(cls, path: str = "results/hw_profile_cpu.json") -> HW:
        d = json.load(open(path))
        return cls(d["triad_GBps_numpy_1thread"], d["gemm_fp32_GFLOPs_blas_all_threads"],
                   d["cores"])


@dataclass
class Params:
    alpha_c: float = 1.0
    alpha_b: float = 1.0
    eff_c: dict[str, float] = field(default_factory=dict)
    eff_b: dict[str, float] = field(default_factory=dict)


def predict(hw: HW, p: Params, name: str, size_bytes: float, threads: int) -> tuple[float, float]:
    """-> (prefill tok/s, decode tok/s) for a single request stream."""
    q = quant_of(name)
    pp = p.eff_c.get(q, 1.0) * (hw.gemm_gflops / hw.cores) * threads**p.alpha_c * 1e9 \
        / (2 * PARAMS[size_of(name)])
    tg = p.eff_b.get(q, 1.0) * hw.triad_gbps * threads**p.alpha_b * 1e9 / size_bytes
    return pp, tg


def load_measurements() -> list[dict]:
    rows: dict[tuple, dict] = {}
    for path in ("results/quant_bench.csv", "results/threads_bench.csv"):
        for r in csv.DictReader(open(path)):
            name = os.path.basename(r["model_filename"]).replace(".gguf", "")
            key = (name, int(r["n_threads"]))
            d = rows.setdefault(key, {"name": name, "threads": int(r["n_threads"]),
                                      "bytes": float(r["model_size"])})
            if int(r["n_prompt"]) > 0:
                d["pp"] = float(r["avg_ts"])
            if int(r["n_gen"]) > 0:
                d["tg"] = float(r["avg_ts"])
    return [d for d in rows.values() if "pp" in d and "tg" in d]


def fit(hw: HW, ms: list[dict]) -> Params:
    """alpha from the 0.5B Q4_K_M thread sweep (log-log slope); eff per quant from 0.5B at t=2."""
    sweep = sorted((m for m in ms if m["name"] == "qwen2.5-0.5b-instruct-q4_k_m"),
                   key=lambda m: m["threads"])

    def slope(key: str) -> float:
        xs = [math.log(m["threads"]) for m in sweep]
        ys = [math.log(m[key]) for m in sweep]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / \
            sum((x - mx) ** 2 for x in xs)

    p = Params(alpha_c=slope("pp"), alpha_b=slope("tg"))
    for m in ms:
        if size_of(m["name"]) == "0.5b" and m["threads"] == 2:
            q = quant_of(m["name"])
            raw = predict(hw, Params(p.alpha_c, p.alpha_b), m["name"], m["bytes"], 2)
            p.eff_c[q], p.eff_b[q] = m["pp"] / raw[0], m["tg"] / raw[1]
    return p
