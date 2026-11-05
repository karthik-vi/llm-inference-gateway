# Standing rules for this repo — read at the start of every session

The project spec is in `docs/PROJECT_BRIEF.md`. The current state is in `PROGRESS.md`.
Start every session by reading both, then continue from the next unfinished item.

## 1. Budget: credits are scarce (~$30 total)
- Finished, pushed, measured work beats breadth. Build in the order the brief gives (Must → Should → Could).
- Don't start a new phase until the current one is pushed and its acceptance check passes. If the budget looks tight, finish and document the current phase rather than starting another.
- Keep context small. Never `cat` large files or full logs; use `head`, `tail`, `grep`, `wc`. Write long outputs to `results/` or `logs/` and read only summaries.
- Run downloads, builds, benchmarks and evals in the background with output going to a log file, then check them with `tail`. Size every benchmark to finish in under 15 minutes in this container. Full-size runs belong in scripts the user runs elsewhere.
- No speculative refactors, no polishing, and no new dependency unless it serves a purpose stated in `docs/DECISIONS.md`.
- If something fails the same way twice: stop, write the blocker in `PROGRESS.md`, push, and move on to the next item.

## 2. Never lose work (the container can disappear at any moment)
- Commit and push to the current branch after every working milestone, and at least every 30–45 minutes of work. Use small Conventional Commits (`feat:`, `fix:`, `bench:`, `docs:`).
- Commit and push before any long or risky step.
- Update `PROGRESS.md` before every push with: Done / In progress / Next step / Blockers / How to resume. A fresh session must be able to continue from `PROGRESS.md` alone.
- Never commit model weights, datasets, or any file over 5 MB. Keep them in gitignored `models/` and `data/`, with download scripts (`make download`).

## 3. Every component must earn its place
- For every component, answer two questions: what problem does it solve, and which metric shows it worked? Record the answers in `docs/DECISIONS.md` in ADR format: Context → Options considered → Decision → Evidence (numbers).
- If a component doesn't move its metric, say so honestly, then disable or remove it. A well-documented negative result is valuable.
- Never add a technology just so it can go on a resume. The user will be asked "why did you use X?" in interviews, and `DECISIONS.md` must hold the answer.

## 4. Honest numbers only
- Every number in the README or `results/RESUME_METRICS.md` must come from a run in this repo. Record with it: the command to reproduce it, the hardware (CPU model, cores, RAM; GPU if any), the model and quantization, the dataset and sample size, and the date.
- Never estimate, round up, or invent a metric. Anything you couldn't run here (e.g. Docker, Kubernetes, GPU) is labeled **"not verified in this environment"**.
- Report the baseline next to every improvement, and use p50/p95/p99, not averages alone.

## 5. Code quality
- Python 3.11+, type hints, `ruff` and `pytest`. Unit-test the core logic: scheduler, router, cache, performance model, eval scorers.
- GitHub Actions runs lint and tests on every push: CPU-only, LLM calls mocked, under 5 minutes.
- Put all settings in one config file (pydantic-settings or YAML). No hard-coded paths or ports.
- Provide a Makefile target for everything a reader would run: `setup`, `download`, `serve`, `bench-*`, `eval`, `test`.

## 6. Docs a recruiter or interviewer can skim in 2 minutes
- `README.md`: the problem and who it's for, a Mermaid architecture diagram, a quickstart, a results table (baseline vs. improved), the key design decisions with links to `DECISIONS.md`, and limitations.
- Also keep: `docs/DECISIONS.md`, `docs/BENCHMARKS.md` (methodology), `docs/DATA.md` (every dataset and model, with its license), `docs/ENVIRONMENT.md`, `PROGRESS.md`, `results/RESUME_METRICS.md`.
- Charts: save PNGs to `results/plots/` (small files only) and embed them in the README.

## 7. End of every session
Update `PROGRESS.md`, push, and reply with a summary of at most 5 lines: what got done, the headline numbers, and the next step.
