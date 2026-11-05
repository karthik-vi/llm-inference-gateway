# PROGRESS

## Done
- Phase 0, 1: env, skeleton, CI, baseline serving + load generator + sweep (ADR-001/002).
- Phase 2 (all six measured, ADR-003..009): prefix routing (negative), admission (positive), gRPC vs polling (no benefit), semantic cache (positive at saturation), quantization (Q4_K_M chosen, speed only), cascade (negative), combined run (not additive).
- Phase 3 (ADR-010): HW microbenchmarks, roofline model (decode held-out error 98% -> 5%, prefill 31% -> 38%), capacity planner CLI (pessimistic: +58..291% p95), gateway overhead +3.8 ms p50 / +9.5 ms p95, py-spy flamegraph.
- Must tier (Phases 0-3) COMPLETE.

## In progress
- Phase 4 (Should) starting.

## Next step
Phase 4 agent + eval harness + quality column; then 5 (observability), 6 (notebooks), 7 only if budget remains. README "predict before you buy hardware" section and final results table still to write.

## Blockers / caveats
- Docker daemon unusable (not verified in this environment).
- Single runs everywhere, no confidence intervals. Admission can shed all LLM traffic when its EWMA is inflated (ADR-009). Planner is pessimistic. Combined run worse than admission alone at 3 rps.
- `make bench-baseline`, `make bench-ablation` targets were assembled from scripts that were run directly; not run end to end via make.
- Tests: router, admission, semcache, perfmodel. Loadgen and SSE proxy untested.

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. `make setup && make download`. A/B: `RATES=2,3 bench/ablate.sh <tag> ENV=...`, `python -m bench.report --tag <tag> --slo 2.0`. Model: `make perfmodel`.
