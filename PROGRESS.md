# PROGRESS

## Done
- Phase 0-3 (Must) complete: env, skeleton, CI, baseline serving + load generator + sweep, all six Phase 2 techniques measured (ADR-003..009), perf model + capacity planner + gateway overhead (ADR-010).
- Phase 4 (Should): support-agent eval harness over tau-bench retail DB/policy (tau-bench-STYLE generated tasks), scorers, mocked-LLM CI test, 6-config quality table (ADR-011; inconclusive, n=24).
- Phase 5 (Should): OTel spans, Prometheus metrics, SLO + burn-rate alerts, Dockerfile/compose/k8s (NOT verified: no Docker), passive circuit breaker, incident drill + postmortem (ADR-012, docs/INCIDENT_DRILL.md).
- Phase 6 (Could): two Colab notebooks written (gpu_serving_benchmark, router_lora_finetune), syntax-checked only, NOT run.
- README, RESUME_METRICS, DECISIONS, BENCHMARKS, DATA, ENVIRONMENT written. CI green on the last completed runs (23-25); run 26 (docs-only) was in progress when last checked.

## In progress
- Nothing.

## Not done
- Phase 7 (voice front-end): NOT started. Reason: heavy ML dependencies (torch, SpeechBrain, Whisper, Piper) vs scarce budget; it is the Could tier.
- Notebook results (`results/gpu_benchmark.json`, `results/router_lora.json`) do not exist until the user runs the notebooks on Colab.

## Next step
1. Run the two notebooks on a free T4 and commit the result JSONs; feed `hw_profile_t4.json` to `perfmodel` (`HW.load(path)`).
2. Fix the weak spots below (in order of value): admission estimator can shed all LLM traffic (ADR-009); latency-aware routing for slow replicas (drill); repeat runs for confidence intervals; a stronger base model or larger task set for the quality eval (`python -m eval.tasks 40`).
3. Phase 7 only if wanted.

## Blockers / caveats
- Docker daemon unusable: Dockerfile, compose, k8s, Prometheus rules, Grafana dashboard are not verified in this environment (alert rules were evaluated offline in Python with scaled windows; `deploy/grafana/` is empty, panels are rendered with matplotlib in results/plots/drill_*.png).
- Single runs everywhere, no confidence intervals; the nominal arrival rate differs from the measured rate.
- `make bench-baseline`, `make bench-ablation`, `make eval` wrap scripts that were run directly; the make targets were not run end to end.
- Planner is pessimistic (+58..291% p95); prefill model does not transfer across model sizes; semantic-cache quality cost unmeasured (0 eligible hits in the agent eval).

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. `make setup && make download`. A/B: `RATES=2,3 bench/ablate.sh <tag> ENV=...`, `python -m bench.report --tag <tag> --slo 2.0`. Model: `make perfmodel`. Agent eval: `make eval`. Drill: `python -m bench.drill --tag X [--breaker]` then `python -m bench.drill_report --tag X`.
