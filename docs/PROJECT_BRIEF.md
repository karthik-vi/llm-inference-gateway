# Project brief: SLO-aware LLM inference gateway, proven on a real support-agent workload

## Pitch
Teams self-host open LLMs for privacy and cost, and they keep running into the same three problems:
- p95 latency blows up under load.
- Compute is wasted re-processing the same prompts.
- Nobody knows how many replicas they actually need.

This project is an **OpenAI-compatible gateway** that sits in front of a pool of self-hosted model replicas. It cuts latency and cost with:
- **KV-cache-aware routing**
- **SLO-based admission control**
- **a semantic cache**
- **a small→large model cascade**

It also ships a **performance model and capacity planner** that predicts how many replicas a workload needs, checked against real measurements.

A multi-turn **customer-support agent** with tools and retrieval is the workload that proves each technique. An **evaluation harness** measures what each optimization costs in quality.

Every result is a before/after against a measured baseline.

**Questions the finished repo answers with numbers:**
1. How much does each serving technique change p95 time-to-first-token (TTFT), goodput, and cost per 1k requests?
2. How many replicas does a given workload need to meet its SLO? Predicted vs. measured.
3. What does each optimization cost in answer quality and task success?

## Hard constraints
- **CPU-only in this container.** All GPU work is written as Colab notebooks for the user to run on a free T4, and labeled as such.
- **Models:** Qwen2.5-0.5B-Instruct and Qwen2.5-1.5B-Instruct (Apache-2.0), as GGUF from the official Qwen Hugging Face repos. Use a small sentence-embedding model (e.g. bge-small-en-v1.5 or all-MiniLM-L6-v2). Don't download anything over ~2 GB.
- **Data:**
  - Workload: the Bitext customer-support dataset on Hugging Face (`bitext/Bitext-customer-support-llm-chatbot-training-dataset`). It has real-style queries across 27 intents.
  - Agent tasks: the τ-bench retail domain (`sierra-research/tau-bench` on GitHub, MIT license), if it's reachable.
  - Record every license in `docs/DATA.md`. If you construct synthetic multi-turn sessions from single-turn data, say so plainly.
- **Network:** If downloads from huggingface.co fail, stop immediately. Write it in `PROGRESS.md`, push, and tell the user to allow `huggingface.co` and `*.hf.co` in the environment's network settings.

## Priorities
- **Must:** Phases 0–3. This is the resume-ready core.
- **Should:** Phases 4–5.
- **Could:** Phases 6–7.

Never start a lower tier while a higher one is unfinished.

## Repo layout
```
gateway/      FastAPI app: router, admission control, semantic cache, cascade, telemetry
control/      gRPC .proto + per-replica sidecar that streams load stats
perfmodel/    microbenchmarks, roofline model, capacity planner CLI
workloads/    trace builder, Poisson load generator / replayer, support agent
eval/         harness, scorers, user simulator
notebooks/    Colab notebooks (GPU benchmark, LoRA fine-tune)
deploy/       Dockerfile, docker-compose, k8s manifests, Prometheus rules, Grafana dashboard
results/      CSV/JSON results, plots/, RESUME_METRICS.md
docs/         DECISIONS.md, BENCHMARKS.md, DATA.md, ENVIRONMENT.md, INCIDENT_DRILL.md
tests/
```

---

## Phase 0: Environment check and skeleton (Must, keep it short)
1. Record the following in `docs/ENVIRONMENT.md`:
   - CPU model and core count, RAM, free disk, Python version
   - whether `docker` works
   - whether github.com and huggingface.co downloads work (test with a tiny file)
2. Create the layout above, plus:
   - `pyproject.toml`, `Makefile`
   - ruff and pytest config
   - a GitHub Actions CI workflow
   - `.gitignore` covering `models/`, `data/`, `logs/`
   - `PROGRESS.md` and an empty `docs/DECISIONS.md`
3. Push.

## Phase 1: Baseline serving and load generator (Must)
**Goal:** the reference curve that every later change is compared against.

**Replicas**
- Build `llama.cpp` from source (GitHub, CPU build).
- Run 2 `llama-server` replicas as separate processes with continuous batching (`--parallel`) and prompt caching on.
- Pin threads per replica so the replicas don't fight over cores. Record the split you chose in `DECISIONS.md`.

**Gateway v0** (FastAPI, fully async)
- Implement an OpenAI-compatible `/v1/chat/completions` with SSE streaming and round-robin routing.
- Propagate client disconnects as upstream cancellation.
- Add per-request timeouts.
- Add basic Prometheus metrics: request count, TTFT and inter-token-latency (ITL) histograms, errors.
- Add OpenTelemetry spans around routing and the upstream call.

**Trace and load generator**
- Build sessions from Bitext: multi-turn conversations sharing a realistic support system prompt, with the intent mix taken from the dataset.
- Use Poisson arrivals at a configurable rate.
- For every request, record: TTFT, ITL, end-to-end latency, tokens in/out, status, and replica.

**Baseline sweep**
- Sweep the arrival rate from light load to overload.
- Plot throughput and goodput vs. p50/p95/p99 TTFT.
- Define the SLO from this data (e.g. p95 TTFT ≤ X s) and record why you chose X.

**Acceptance:** `make bench-baseline` reproduces the curve. Numbers and the plot are in `results/` and `RESUME_METRICS.md`.

## Phase 2: Optimizations, each A/B tested against the baseline (Must)
Each item gets:
- a `DECISIONS.md` entry
- a before/after row in `results/ablation.csv`
- a toggle in the config, so the ablation can be reproduced

Keep only what helps, and document the ones that don't.

**a. KV-cache / prefix-aware routing**
- **What:** Send requests from the same session, or with the same long prefix, to the replica that already holds that prefix in its KV cache. Use consistent hashing on the prefix, with a load-aware fallback when the preferred replica is saturated.
- **Metric:** p95 TTFT and the number of prefill tokens recomputed, vs. round-robin at the same load.

**b. SLO-aware admission control**
- **What:** Give each request a deadline. Estimate its queue wait from live replica stats. When the SLO can't be met, either reject early with `429 Retry-After` or downgrade to the 0.5B model, instead of letting every request time out.
- **Metric:** goodput (requests meeting the SLO per second) under overload, vs. baseline.

**c. gRPC control plane**
- **What:** A sidecar per replica streams load stats to the gateway over a bidirectional gRPC stream. Stats: active slots, queue depth, cached prefix hashes, tokens/s. The protobuf schema lives in `control/`.
- **Why:** Routing (a) and admission (b) need fresh, typed, low-overhead load signals.
- **Metric:** compare against polling each replica's HTTP `/metrics`. Measure signal staleness and overhead for both, and keep whichever wins with evidence.

**d. Semantic cache**
- **What:** Embed normalized single-turn FAQ-type user messages, store them in FAISS, and serve a cached answer above a similarity threshold. Never use the cache for turns that depend on account state or earlier turns.
- **Tuning:** Use Bitext intent labels as ground truth. Plot cache hit rate vs. wrong-answer rate across thresholds, and pick an operating point.
- **Metric:** % of LLM calls avoided, cost per 1k requests, p95.

**e. Quantization**
- **What:** Compare F16, Q8_0 and Q4_K_M for both models on memory, tokens/s and TTFT. Phase 4 adds quality.
- **Decision:** Choose a quantization per tier, with evidence.

**f. Model cascade**
- **What:** The 0.5B model handles routing and easy intents, and escalates hard turns to the 1.5B model. Start with a prompt-based router; Phase 6 adds a fine-tuned one.
- **Metric:** cost and p95 vs. always using 1.5B. The quality delta is filled in by Phase 4.

**Acceptance:** `make bench-ablation` produces the full table. The README results table shows baseline vs. each technique vs. all combined.

## Phase 3: Performance model and capacity planner (Must)
**Microbenchmarks.** Measure this CPU's memory bandwidth (STREAM-style triad) and GEMM throughput (numpy/BLAS).

**Analytical roofline model.** Predict tokens/s and TTFT for each model × quantization × batch size × thread count:
- Prefill is roughly compute-bound: about 2 × params FLOPs per token.
- Decode is roughly memory-bandwidth-bound: bytes of weights plus KV cache read per token, divided by bandwidth.
- Add a per-request overhead term.

**Correlation.**
- Compare the predictions with the Phase 1–2 measurements, and report the error % per configuration.
- Explain the biggest misses: thread contention, cache effects, batching, or tokenizer overhead.
- Refine the model once, and report error before and after.

**Capacity planner CLI.**
- **Input:** arrival rate, prompt and output length distributions, SLO.
- **Output:** replicas and threads needed, plus the predicted p95 TTFT. Use queueing (M/M/c or simulation) on top of the service-time model.
- **Validation:** check it against 2–3 measured operating points.
- **Wiring:** use the same service-time model in admission control (2b).

**Gateway overhead.**
- Profile the gateway under load with `py-spy` and save a flamegraph SVG.
- Report the gateway's own added latency at p50/p95, and fix the top hotspot if there is a meaningful one.

**Acceptance:** `make perfmodel` prints the predicted vs. measured table. The README has a "predict before you buy hardware" section.

## Phase 4: Support-agent workload and evaluation harness (Should)
**Agent.** A multi-turn customer-support agent that calls the gateway, with:
- tool calls against a small simulated order/account backend (SQLite)
- retrieval over the policy document

Use τ-bench retail data, tasks and policy if reachable. Otherwise, build a backend from Bitext intents and document that choice.

**Eval harness.** Score each conversation on:
- task success (correct final DB state or correct action)
- tool-call validity (schema-valid JSON, correct tool)
- grounding of policy answers against the retrieved text
- turns, tokens, latency, and cost

The user simulator is the local model with fixed seeds.

**Quality cost of optimizations.** Run the harness on a subset that finishes in under 20 minutes here, and provide a script for the full run elsewhere. Then fill in the quality column for Phase 2's quantization, cascade and semantic cache. This is the latency/cost vs. quality trade-off table.

**CI.** Run a tiny eval with a mocked LLM on every push, so regressions in agent logic or scoring are caught.

## Phase 5: Observability, SLOs and deployment (Should)
**Telemetry.**
- **OpenTelemetry spans:** admission, cache lookup, routing decision, queue wait, upstream TTFT, decode.
- **Prometheus metrics:** goodput, cache hit rate, per-replica load, cascade escalation rate.

**SLO and alerting.**
- Write the SLO as an error budget (e.g. 99% of requests within the TTFT target over 30 days).
- Add multi-window burn-rate alert rules.
- Export a Grafana dashboard JSON. If Grafana can't run here, render equivalent matplotlib panels from recorded metrics.

**Incident drill.**
- During a load run, inject a fault: kill one replica, then separately throttle one replica's CPU.
- Show detection through metrics and alerts, and root-cause through traces.
- Measure the recovery behavior of routing and admission control.
- Write a short blameless postmortem in `docs/INCIDENT_DRILL.md`.

**Deployment.** Write a Dockerfile, a docker-compose file (gateway, 2 replicas, Prometheus, Grafana, OTel collector), and k8s manifests. Verify what you can here and label the rest "not verified in this environment".

## Phase 6: Colab notebooks — written here, run by the user on a free GPU (Could)
Each notebook must have:
- a runtime estimate
- clear "run all" instructions
- output saved to a results JSON that the user commits back to `results/`

**`notebooks/gpu_serving_benchmark.ipynb`**
- Replay the same trace against vLLM on a T4 with the same models.
- Profile with `torch.profiler`.
- Compare GPU vs. CPU cost per 1k requests, and feed the measured numbers back into the perf model as a second hardware profile.

**`notebooks/router_lora_finetune.ipynb`**
- LoRA fine-tune Qwen2.5-0.5B (transformers, datasets, peft) as the cascade router / intent classifier on the Bitext train split.
- Evaluate on a held-out split vs. the prompt-only router.
- Export to GGUF so the gateway can use it.
- **Stretch:** a short GRPO run (TRL) rewarding valid tool-call JSON and the correct tool.

## Phase 7: Voice front-end (Could, only if credits remain)
**Pipeline:** Silero VAD → speaker-verification gate → faster-whisper STT → gateway → Piper TTS.
- The speaker-verification gate uses SpeechBrain ECAPA with an enrolled user.
- **Purpose of the gate:** ignore background speakers and avoid wasting STT/LLM compute on speech not directed at the agent.

**Metrics:**
- WER on a LibriSpeech test-clean subset
- speaker-verification EER on LibriSpeech trials
- end-to-end time-to-first-audio

---

## Definition of done
- `README.md` follows the CLAUDE.md rules: architecture diagram, results table vs. baseline, decisions, limitations.
- `results/RESUME_METRICS.md` lists every headline number with its reproduction command and hardware.
- `PROGRESS.md` says exactly what is done, what is not, and why.
