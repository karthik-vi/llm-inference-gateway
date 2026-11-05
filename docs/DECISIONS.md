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
