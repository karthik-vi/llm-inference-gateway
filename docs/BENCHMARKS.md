# Benchmark methodology

- **Load:** session arrivals are Poisson; request rate = session rate x mean turns. Each session sends its turns sequentially with exponential think time (mean 2 s). The "offered" rate is therefore *nominal*: sessions finish after the 60 s arrival window, so the measured `arrival_rps` differs (see results/baseline_sweep.csv). Throughput/goodput use the measured span (first start to last finish).
- **Request:** ~200-token prompt (system prompt + history), `max_tokens=32`, temperature 0, streaming. Client timeout 30 s; at drain, unfinished sessions are dropped (their completed requests are kept).
- **Goodput:** completed requests with TTFT <= SLO, per second.
- **Single run per rate, seed 1.** No repeats, so no confidence intervals; treat small differences as noise.
- Reproduce: `make bench-baseline` (about 11 min).

## Later phases
- **A/B runs** (`bench/ablate.sh`): fresh replicas per config (so KV caches do not carry over), same trace and seed, one run per rate. Baseline rows for admission/cache/cascade comparisons come from the Phase 1 sweep (older runs of 0.5-3 req/s predate the loadgen drain fix).
- **Semantic cache runs** pre-warm the cache with 164 cacheable first-turn queries from sessions the test never uses (`bench/warm_cache.py`).
- **llama-bench** (`bench/quant.sh`): pp256/tg32, 3 repetitions, 2 threads. **Microbenchmarks**: numpy triad (single thread) and BLAS GEMM.
- **Overhead** (`bench/overhead.sh`): mock upstream with ~1 ms/token, 748 requests direct vs via gateway, py-spy flamegraph.
- **Agent eval** (`eval/`): 24 tasks, temperature 0, seed 0, 2 workers; user-simulator paraphrases cached once. **Drill** (`bench/drill.py`): 200 s timeline with scraped metrics every 2 s; alert rules evaluated offline.
