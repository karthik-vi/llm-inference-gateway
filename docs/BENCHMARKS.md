# Benchmark methodology

- **Load:** session arrivals are Poisson; request rate = session rate x mean turns. Each session sends its turns sequentially with exponential think time (mean 2 s). The "offered" rate is therefore *nominal*: sessions finish after the 60 s arrival window, so the measured `arrival_rps` differs (see results/baseline_sweep.csv). Throughput/goodput use the measured span (first start to last finish).
- **Request:** ~200-token prompt (system prompt + history), `max_tokens=32`, temperature 0, streaming. Client timeout 30 s; at drain, unfinished sessions are dropped (their completed requests are kept).
- **Goodput:** completed requests with TTFT <= SLO, per second.
- **Single run per rate, seed 1.** No repeats, so no confidence intervals; treat small differences as noise.
- Reproduce: `make bench-baseline` (about 11 min).
