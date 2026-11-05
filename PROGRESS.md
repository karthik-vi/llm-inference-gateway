# PROGRESS

## Done
- Phase 0: environment check (docs/ENVIRONMENT.md), repo skeleton, pyproject, Makefile, ruff/pytest config, CI workflow, .gitignore, DECISIONS stub.

## In progress
- Phase 1 not started.

## Next step
- Phase 1: build llama.cpp (CPU), download Qwen2.5 GGUFs + Bitext, run 2 replicas, gateway v0, load generator, baseline sweep.

## Blockers
- None. Note: 4 vCPUs only, so 2 replicas x 2 threads; docker unusable.

## How to resume
Read CLAUDE.md, docs/PROJECT_BRIEF.md, this file. Then start Phase 1 (`make setup` first).
