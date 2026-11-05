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
