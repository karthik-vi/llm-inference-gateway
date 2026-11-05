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

## Phases 3-5 (hardware: same Xeon 4 vCPU, 15 GiB; 2026-11-05; single runs)
| claim | number | reproduce | notes |
|---|---|---|---|
| Semantic cache, goodput @ nominal 2 req/s | 0.89 -> 1.55 req/s; p95 TTFT 4.03 -> 1.42 s; 32/101 LLM calls avoided | `RATES=1,2,3 WARM=1 bench/ablate.sh sem GATEWAY_SEMCACHE=1` | bge-small-en-v1.5, thr 0.92, cache pre-warmed with 164 queries; at nominal 1 req/s p95 got worse (1.53 -> 2.52 s) |
| Semantic cache offline threshold curve | 91.3% hit, 0.15% wrong (intent proxy) at 0.92 | `python -m eval.semcache_tune` | 8000 indexed / 3000 queries; Bitext is templated so optimistic |
| Quantization (llama-bench, 2 threads) | 0.5B decode F16 13.8, Q8_0 20.5, Q4_K_M 25.0 tok/s; 1.5B Q4_K_M 11.6, Q8_0 7.1 | `bench/quant.sh` | 1.5B F16 not run (>2 GB) |
| Cascade vs always-1.5B @ 0.5 req/s | p95 TTFT 3.55 s -> 8.21 s (worse) | `bench/cascade_ab.sh` | router acc 85% (proxy label) |
| gRPC vs HTTP polling | equal staleness (age p50 ~ period/2 + 3 ms); 16 vs 2583 bytes/update | `python -m bench.control_plane` | same host |
| Perf model, held-out 1.5B decode error | 98% -> 5% after one refinement; prefill 31% -> 38% | `make perfmodel` | fitted on 0.5B only |
| Planner | saturation 1.68 vs measured 1.6-1.7 req/s; p95 TTFT error +58/+67/+291% | `python -m perfmodel.validate` | pessimistic |
| Gateway overhead | +3.8 ms p50 / +9.5 ms p95 TTFT (40 req/s, mock upstream) | `bench/overhead.sh` | |
| Agent quality | 0.5B 1/8 vs 1.5B 4/8 policy questions; lookup/cancel 0/8 all | `make eval` | n=24, inconclusive |
| Incident drill | kill: ReplicaErrors alert 0.3 s; throttle: burn alert 18.7-30.7 s; breaker 51.7% -> 27.8% errors | `python -m bench.drill --tag X [--breaker]` | alerts evaluated offline, windows scaled |
