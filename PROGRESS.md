# PROGRESS

## Done
- Phase 0: env check, skeleton, CI, Makefile, ruff/pytest.
- Phase 1 (acceptance met): llama.cpp CPU build, 2 replicas (`scripts/replicas.sh`), gateway v0 (round-robin, SSE, upstream cancel on disconnect via closing the stream, timeouts, Prometheus, OTel spans), synthetic multi-turn trace builder, Poisson load generator, baseline sweep + report, SLO chosen (p95 TTFT <= 2 s), results in `results/`, docs (DECISIONS ADR-001/002, BENCHMARKS, DATA, ENVIRONMENT), README.
- Headline: baseline saturates at ~1.6-1.7 req/s; goodput peaks 0.93 req/s then collapses to 0.06 at overload.

## In progress
- Nothing.

## Next step
- Phase 2 (Must), in order: (a) prefix-aware routing (consistent hash + load-aware fallback, config toggle, ablation row in `results/ablation.csv`), (b) SLO admission control, (c) gRPC control plane vs HTTP polling, (d) semantic cache, (e) quantization, (f) cascade. Then Phase 3.

## Blockers / caveats
- Docker daemon unusable (not verified in this environment).
- `make bench-baseline` was assembled from the pieces that were run by hand; the Makefile target itself has NOT been run end to end. Run it once before relying on it.
- Gateway unit tests cover only the router; loadgen/summarize and the SSE proxy have no tests yet (CI mocks needed). The 1.5B GGUF is downloaded but unused.
- Replica threads are not core-pinned; ADR-001 compared no alternatives.
- Upstream cancellation on client disconnect is implemented but not verified by a test.

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. `make setup && make download`, then start Phase 2a.
