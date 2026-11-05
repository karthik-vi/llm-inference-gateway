# Decisions (ADR log)

Format per entry: Context -> Options considered -> Decision -> Evidence (numbers).

## ADR-001: Replica layout - 2 x llama-server, 2 threads, 4 slots each
- **Context:** Container has 4 vCPUs; the brief requires 2 replicas without core contention.
- **Options:** (a) 2 replicas x 2 threads; (b) 1 replica x 4 threads; (c) 2 x 4 threads (oversubscribed).
- **Decision:** (a), `--cont-batching --cache-prompt`, `-np 4`, 1024 ctx/slot. Threads are not hard-pinned (no `taskset` yet); the split is by thread count only.
- **Evidence:** Only (a) was run. (b) and (c) were not compared, so this choice is untested against alternatives. Revisit in Phase 3 microbenchmarks.

## ADR-002: Baseline SLO = p95 TTFT <= 2.0 s
- **Context:** Goodput needs a TTFT target, taken from the baseline curve (Qwen2.5-0.5B Q4_K_M, round-robin).
- **Decision:** 2.0 s. Light-load p95 TTFT is 1.35 s (nominal 0.5 rps) and 1.54 s (nominal 1.0 rps), so 2 s is met with headroom before the knee; at nominal 2.0 rps p95 is 4.03 s.
- **Evidence:** results/baseline_sweep.csv. Goodput peaks at 0.93 req/s (nominal 1.0) and falls to 0.06 req/s at nominal 6.0 (overload: 54 of 247 requests errored/timed out, p95 TTFT 29.8 s).
- **Caveat:** 2.0 s is a judgement call, not derived from a user-facing requirement. The unloaded TTFT is already ~0.6 s p50 because the CPU prefills ~200 prompt tokens slowly.

## ADR-003: Prefix-aware routing (consistent hash on system+first user message, load fallback)
- **Problem / metric:** avoid re-prefilling a session's history on the other replica. Metric: prefill tokens recomputed per request (llama-server `timings.prompt_n`) and p95 TTFT vs round-robin at the same nominal load.
- **Options:** round-robin (baseline); consistent hash on the session prefix with fallback to least-loaded at >= 6 in flight (implemented, `gateway.routing: prefix`).
- **Evidence** (results/ablation.csv, fresh replicas per config, same trace/seed, one run each):

  | nominal rps | routing | prefill tok/req | p95 TTFT | goodput |
  |---|---|---|---|---|
  | 1.0 | round_robin | 82.8 | 1.74 s | 0.82 |
  | 1.0 | prefix | 72.2 (-13%) | 2.29 s | 0.72 |
  | 2.0 | round_robin | 69.5 | 5.14 s | 0.85 |
  | 2.0 | prefix | 63.7 (-8%) | 5.77 s | 0.73 |
- **Result: negative / inconclusive.** Recomputed prefill per request fell 8-13%, but p95 TTFT and goodput were not better (slightly worse), within what single-run noise could explain (completed-request counts differ between runs: 65 vs 60, 109 vs 146). Requests were evenly split across replicas (31/29, 78/68), so imbalance is not the cause.
- **Likely reason (hypothesis, not tested):** the ~100-token system prompt is shared by every session and is already cached on both replicas; only the short per-session history (1-3 turns) benefits from stickiness, so the ceiling is small, and llama-server's per-slot prompt cache already catches some reuse under round-robin (cached tokens were 60% of prompt tokens under RR at 1.0 rps).
- **Decision:** keep the code and toggle, default stays `round_robin`. Not claimed as an improvement. A longer-history workload or repeated runs would be needed to show a benefit.

## ADR-004: SLO-aware admission control (reject with 429 + Retry-After)
- **Problem / metric:** past saturation every request queues and misses the SLO (baseline goodput 0.06 req/s at nominal 6.0). Metric: goodput (completed requests with TTFT <= 2.0 s per second) under overload vs baseline.
- **Options:** none (baseline); estimate TTFT = ttft_base + queue_depth x service_time / slots from gateway in-flight counts and EWMAs, reject when estimate > SLO (implemented, `gateway.admission`, env `GATEWAY_ADMISSION=1`). Downgrade-to-0.5B was **not** implemented: replicas already serve the 0.5B model (cascade is 2f).
- **Evidence** (results/ablation.csv, one run per rate, fresh replicas for the adm runs, same trace/seed; the "off" rows are the Phase 1 baseline runs):

  | nominal rps | goodput off | goodput on | p95 TTFT off | p95 TTFT on | rejected/failed (on) |
  |---|---|---|---|---|---|
  | 2.0 | 0.89 | 1.08 | 4.03 s | 3.81 s | 11 of 107 |
  | 3.0 | 0.24 | 1.37 | 16.2 s | 2.52 s | 34 of 155 |
  | 4.0 | 0.19 | 1.40 | 27.7 s | 2.81 s | 48 of 183 |
  | 6.0 | 0.06 | 1.04 | 29.8 s | 7.13 s | 95 of 241 |
- **Result: positive under overload.** Goodput rises from 0.24 to 1.37 req/s at nominal 3.0 and from 0.06 to 1.04 at 6.0, at the cost of rejecting 22-39% of requests. At nominal 2.0 the gain is smaller (0.89 to 1.08) and p95 stays above the SLO.
- **Caveats:** (1) The load generator ends a session when a request is rejected (the client gives up and does not retry), so measured arrival rates are lower with admission on; "rejected/failed" counts all non-ok requests. (2) Admitted p95 exceeded the 2.0 s SLO at 2.0 and 6.0 rps (3.81 s, 7.13 s): the estimator uses EWMAs and lags load changes, and the margin is 1.0. (3) Off and on runs were separate runs (the off runs of 0.5-3 rps predate the loadgen drain fix), single run each, no confidence intervals. (4) The estimator uses crude in-flight counts; Phase 3's service-time model is meant to replace it.

## ADR-005: Semantic cache (bge-small-en-v1.5 via fastembed + FAISS flat IP, threshold 0.92)
- **Problem / metric:** FAQ-style first turns repeat across users; re-running the LLM wastes compute. Metrics: % of LLM calls avoided, p95 TTFT / goodput vs baseline, wrong-answer rate vs threshold.
- **Dependencies (why):** `fastembed` (ONNX, ~4 ms/query on this CPU; avoids torch), `faiss-cpu` (nearest-neighbour search). Embedding model BAAI/bge-small-en-v1.5 (MIT).
- **Safety rule:** cache only single-turn messages with no assistant history, no digits and no account-state wording ("my order", "tracking", ...). Multi-turn and account-dependent turns always go to the LLM (unit-tested).
- **Threshold tuning** (`python -m eval.semcache_tune`; results/semcache_tuning.csv, plots/semcache_tuning.png): 8000 indexed vs 3000 held-out cacheable Bitext queries; "wrong" = nearest cached query has a different Bitext intent (a proxy: same intent does not guarantee an identical answer).

  | threshold | hit rate | wrong of hits |
  |---|---|---|
  | 0.88 | 97.2% | 0.51% |
  | 0.90 | 95.0% | 0.35% |
  | 0.92 | 91.3% | 0.15% |
  | 0.96 | 71.8% | 0.14% |
  | 0.98 | 44.3% | 0.0% |
  Chosen **0.92**: best hit rate before the wrong-answer rate flattens. **These offline hit rates are optimistic**: Bitext is templated paraphrases of 27 intents, so near-duplicates are abundant; real traffic would hit far less.
- **Online A/B** (results/ablation.csv; cache pre-warmed with 164 cacheable queries from sessions not in the test; entries written through on each miss; same trace/seed; baseline = Phase 1 runs; one run each):

  | nominal rps | LLM calls avoided | p95 TTFT base -> cache | goodput base -> cache |
  |---|---|---|---|
  | 1.0 | 10/78 = 13% | 1.53 s -> 2.52 s | 0.93 -> 0.95 |
  | 2.0 | 32/101 = 32% | 4.03 s -> 1.42 s | 0.89 -> 1.55 |
  | 3.0 | 46/173 = 27% | 16.2 s -> 9.24 s | 0.24 -> 0.80 |
- **Result: helps at and above saturation, no benefit (and p95 worse, likely noise or embedding CPU contention) at light load.** Only first-turn state-free messages are cacheable, which caps online hit rate at roughly a third of requests. Cached answers are the LLM's own earlier 32-token answers, so quality cost on the support agent is measured in Phase 4. Cost per 1k requests is not measured separately: avoided LLM calls translate directly to avoided replica compute, which Phase 3's service-time model will convert into replicas.

## ADR-006: Quantization per tier (speed/memory only; quality column filled in Phase 4)
- **Problem / metric:** pick the GGUF quantization for each model tier. Metrics: model memory (file size), prompt-processing tokens/s (pp256, TTFT driver), decode tokens/s (tg32), via `llama-bench -t 2 -r 3` (mean +- stddev over 3 reps; results/quant_bench.csv; reproduce `bench/quant.sh`; Xeon @ 2.80GHz, 2 threads, llama.cpp build 8bed7cf, 2026-11-05).
- **Evidence:**

  | model | quant | size | pp256 tok/s | tg32 tok/s |
  |---|---|---|---|---|
  | 0.5B | F16 | 1260 MB | 159.8 +- 7.1 | 13.8 +- 0.3 |
  | 0.5B | Q8_0 | 670 MB | 142.6 +- 20.0 | 20.5 +- 0.4 |
  | 0.5B | Q4_K_M | 485 MB | 135.4 +- 13.3 | 25.0 +- 1.4 |
  | 1.5B | Q4_K_M | 1111 MB | 65.1 +- 2.1 | 11.6 +- 0.4 |
  | 1.5B | Q8_0 | 1889 MB | 39.8 +- 2.2 | 7.1 +- 0.3 |
  | 1.5B | F16 | not run: ~3 GB download exceeds the 2 GB rule | | |
- **Result:** decode is memory-bandwidth-bound (tg rises as size falls: 13.8 -> 20.5 -> 25.0 tok/s for 0.5B). Prefill is compute-bound and roughly flat across quants for 0.5B (differences within noise), but Q8_0 is slower than Q4_K_M for 1.5B (39.8 vs 65.1).
- **Decision:** Q4_K_M for both tiers (fastest decode, smallest memory; the replicas already run it). Q8_0 may only be justified if Phase 4 shows a quality gap; until then this is a speed/memory decision with **no quality evidence**.

## ADR-008: Small->large model cascade (rule router and prompt-based 0.5B router)
- **Problem / metric:** serve easy turns on the 0.5B model and escalate hard ones to 1.5B, to cut cost/latency vs always using 1.5B. Metrics: p95 TTFT and goodput vs always-1.5B at the same load; escalation rate; router accuracy. Quality delta is Phase 4's job.
- **Options:** always-1.5B on 2 replicas (baseline); cascade on 1x0.5B + 1x1.5B replica with a **rule** router (HARD = multi-turn or state/account wording) or a **prompt-based 0.5B** router (one extra `max_tokens=3` call; multi-turn is always HARD). Implemented: `gateway.cascade` (`off|rule|llm`), `config_cascade.yaml`, `config_large.yaml`.
- **Router accuracy** (`python -m eval.cascade_router_eval`, 200 trace turns, label = rule label as a proxy for "hard"): accuracy 85.0%, hard recall 88.7%, easy recall 78.9% (multi-turn turns are escalated by rule, which inflates this).
- **Evidence** (results/ablation.csv, one run each, fresh replicas; hardware 4 vCPU, 2 threads/replica; SLO 2 s):

  | nominal rps | config | escalated to 1.5B | p50 TTFT | p95 TTFT | goodput |
  |---|---|---|---|---|---|
  | 0.5 | always-1.5B (2 replicas) | 100% | 1.73 s | 3.55 s | 0.26 |
  | 0.5 | cascade, rule | 28/41 = 68% | 3.30 s | 8.21 s | 0.19 |
  | 0.5 | cascade, LLM router | 30/41 = 73% | 2.76 s | 9.68 s | 0.15 |
  | 1.0 | always-1.5B | 100% | 2.54 s | 8.38 s | 0.22 |
  | 1.0 | cascade, rule | 42/64 = 66% | 5.84 s | 22.4 s | 0.23 |
  | 1.0 | cascade, LLM router | 42/64 = 66% | 7.04 s | 27.2 s | 0.22 |
  For reference, always-0.5B on 2 replicas (Phase 1 baseline) had p95 TTFT 1.34 s / 1.53 s at nominal 0.5 / 1.0 rps.
- **Result: negative.** With this workload about two thirds of turns are multi-turn or state-dependent (HARD), so the single 1.5B replica receives ~2/3 of traffic and becomes the bottleneck; the cascade is *slower* than simply running 2x 1.5B, and the LLM router adds an extra model call without better routing than the rule. The topology was not sized to the traffic split (a 1:2 small:large replica ratio, or more cores, was not tried). Cost per 1k requests was not measured, so no cost claim is made.
- **Decision:** keep the code, default `cascade: off`. The cascade only makes sense when most turns are easy or replicas are provisioned in proportion to the escalation rate; this is exactly what the Phase 3 capacity planner should size. Quality of 0.5B vs 1.5B is not yet measured (Phase 4).
