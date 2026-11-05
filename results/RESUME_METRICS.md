# Resume metrics (every number is from a run in this repo)

**Hardware:** Intel Xeon @ 2.80GHz, 4 vCPUs (AVX-512F), 15 GiB RAM, no GPU. **Model:** Qwen2.5-0.5B-Instruct Q4_K_M, 2 llama.cpp replicas (2 threads, 4 slots each). **Data:** 400 synthetic multi-turn sessions from Bitext (seed 0). **Date:** 2026-11-05. **Reproduce:** `make bench-baseline`. Single run per rate; SLO = p95 TTFT <= 2.0 s.

## Baseline (round-robin gateway v0)
| nominal rps | measured req/s | p50 TTFT | p95 TTFT | p99 TTFT | goodput req/s | errors |
|---|---|---|---|---|---|---|
| 0.5 | 0.55 | 0.62 s | 1.35 s | 1.74 s | 0.55 | 0 |
| 1.0 | 0.94 | 0.64 s | 1.54 s | 1.83 s | 0.93 | 0 |
| 2.0 | 1.57 | 1.52 s | 4.03 s | 4.17 s | 0.89 | 0 |
| 3.0 | 1.56 | 7.15 s | 16.2 s | 17.2 s | 0.24 | 0 |
| 4.0 | 1.76 | 17.2 s | 27.7 s | 29.0 s | 0.19 | 7 |
| 6.0 | 2.07 | 21.5 s | 29.8 s | 29.9 s | 0.06 | 54 |

Headline: the 2-replica CPU baseline saturates at about 1.6-1.7 completed req/s; beyond that p95 TTFT grows from 1.5 s to ~30 s and goodput collapses (0.93 -> 0.06 req/s). This is the curve Phase 2 optimizations must beat. Plot: results/plots/baseline_sweep.png.

## Phase 2 ablations (same hardware/model/trace; reproduce: `RATES=... bench/ablate.sh <tag> ENV=...`; one run each; full rows in results/ablation.csv, details in docs/DECISIONS.md ADR-003/004)
| technique | baseline | with technique | verdict |
|---|---|---|---|
| SLO admission control, goodput at nominal 3.0 rps | 0.24 req/s (p95 TTFT 16.2 s) | 1.37 req/s (p95 TTFT 2.52 s), 22% of requests rejected | helps under overload |
| SLO admission control, goodput at nominal 6.0 rps | 0.06 req/s (p95 29.8 s) | 1.04 req/s (p95 7.13 s), 39% rejected | helps, p95 still above SLO |
| Prefix-aware routing, prefill tokens/request at 1.0 rps | 82.8 | 72.2 (-13%), but p95 TTFT 1.74 s -> 2.29 s | inconclusive/negative, not claimed |
