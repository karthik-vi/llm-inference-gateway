"""Phase 3 microbenchmarks: memory bandwidth (STREAM-style triad) and GEMM throughput (BLAS).
Writes results/hw_profile_cpu.json."""
from __future__ import annotations

import json
import time

import numpy as np


def triad_gbs(n: int = 40_000_000, reps: int = 5) -> float:
    a = np.zeros(n, dtype=np.float32)
    b = np.random.rand(n).astype(np.float32)
    c = np.random.rand(n).astype(np.float32)
    best = 0.0
    for _ in range(reps):
        t = time.perf_counter()
        np.multiply(c, 3.0, out=a)   # a = b + 3*c in two passes (numpy has no fused triad)
        np.add(a, b, out=a)
        dt = time.perf_counter() - t
        # passes: read c, write a, read a, read b, write a = 5 arrays x 4 bytes
        best = max(best, 5 * n * 4 / dt / 1e9)
    return best


def gemm_gflops(m: int = 1024, reps: int = 5) -> float:
    a = np.random.rand(m, m).astype(np.float32)
    b = np.random.rand(m, m).astype(np.float32)
    a @ b
    best = 0.0
    for _ in range(reps):
        t = time.perf_counter()
        a @ b
        best = max(best, 2 * m**3 / (time.perf_counter() - t) / 1e9)
    return best


if __name__ == "__main__":
    import os

    out = {"cpu": "Intel Xeon @ 2.80GHz (4 vCPU)", "cores": os.cpu_count(),
           "triad_GBps_numpy_1thread": round(triad_gbs(), 2),
           "gemm_fp32_GFLOPs_blas_all_threads": round(gemm_gflops(), 1)}
    json.dump(out, open("results/hw_profile_cpu.json", "w"), indent=1)
    print(out)
