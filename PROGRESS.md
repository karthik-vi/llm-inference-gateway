# PROGRESS

## Done
- Phase 0: env check, skeleton, CI, Makefile, ruff/pytest.
- Phase 1 (acceptance met): llama.cpp CPU build, 2 replicas (`scripts/replicas.sh`), gateway v0 (round-robin, SSE, upstream cancel on disconnect via closing the stream, timeouts, Prometheus, OTel spans), synthetic multi-turn trace builder, Poisson load generator, baseline sweep + report, SLO chosen (p95 TTFT <= 2 s), results in `results/`, docs (DECISIONS ADR-001/002, BENCHMARKS, DATA, ENVIRONMENT), README.
- Headline: baseline saturates at ~1.6-1.7 req/s; goodput peaks 0.93 req/s then collapses to 0.06 at overload.

- Phase 2a prefix-aware routing: implemented + tested, A/B negative/inconclusive (ADR-003), default off.
- Phase 2b SLO admission control: implemented + tested; goodput 0.24 -> 1.37 req/s at nominal 3 rps, 0.06 -> 1.04 at 6 rps (ADR-004).

## In progress
- Phase 2 is PARTIAL (a, b done). Not started: c gRPC control plane vs HTTP polling, d semantic cache, e quantization, f cascade; `make bench-ablation` not wired.

## Next step
- 2d semantic cache (biggest expected win on FAQ intents; needs bge-small/MiniLM + FAISS, justify in ADR), then 2e quantization (cheap: 3 GGUF variants), 2f cascade, 2c gRPC last. Wire `make bench-ablation` (uses bench/ablate.sh). Then Phase 3.

## Blockers / caveats
- Docker daemon unusable (not verified in this environment).
- `make bench-baseline` / ablation targets not run end to end via make; bench/ablate.sh was run directly.
- Tests cover router + admission only; loadgen and the SSE proxy are untested. Upstream cancel on disconnect unverified.
- Single run per config, no confidence intervals; admitted p95 can exceed the SLO (estimator lag).
- Replica threads not core-pinned; 1.5B GGUF downloaded but unused.

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. `make setup && make download`. A/B runs: `RATES=2,3 bench/ablate.sh <tag> GATEWAY_ROUTING=... GATEWAY_ADMISSION=1`, then `python -m bench.report --tag <tag> --slo 2.0`.
