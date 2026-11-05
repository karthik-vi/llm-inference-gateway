# PROGRESS

## Done
- Phase 0: env check (docs/ENVIRONMENT.md), skeleton, CI, Makefile, ruff/pytest.
- Phase 1 (partial): llama.cpp built (vendor/, gitignored), Qwen2.5 0.5B/1.5B Q4_K_M + Bitext downloaded (`make download`), gateway v0 (round-robin, SSE, timeouts, Prometheus, OTel spans), trace builder (synthetic multi-turn from Bitext), Poisson load generator, sweep + report scripts. Smoke test OK (10/10 requests).

## In progress
- Baseline sweep running: `python -m bench.sweep --tag baseline` (rates 0.5,1,2,3,4,6; 60s each) -> results/raw/baseline_*.csv, log logs/sweep_baseline.log.

## Next step
1. When sweep finishes: choose SLO from data, run `python -m bench.report --tag baseline --slo X`, record in DECISIONS.md (thread split 2x2, SLO choice) and results/RESUME_METRICS.md.
2. Wire `make bench-baseline` (replicas.sh start, gateway, trace, sweep, report). Add README, docs/BENCHMARKS.md, docs/DATA.md.
3. Then Phase 2.

## Blockers
- None. Docker unusable here (not verified in this environment).

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. `make setup && make download`, `scripts/replicas.sh start`, `python -m gateway.main &`, then continue the Next step list.
