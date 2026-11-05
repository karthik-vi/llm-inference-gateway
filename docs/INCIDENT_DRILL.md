# Incident drill: replica kill and replica CPU throttle (blameless postmortem)

**What this is:** a controlled fault-injection run on this repo's 4-vCPU container, not a production incident.
Setup: 2 llama.cpp replicas (Qwen2.5-0.5B Q4_K_M, 2 threads each), gateway with round-robin routing, no admission control,
nominal 1.0 req/s of synthetic Bitext sessions for 200 s. Faults are injected on replica `r1` only.
Reproduce: `python -m bench.drill --tag nobreaker` and `python -m bench.drill --tag breaker --breaker`, then
`python -m bench.drill_report --tag <tag>` (raw data in `results/drill_<tag>/`, panels in `results/plots/drill_<tag>.png`).
**Single run per variant; windows contain 28-46 requests, so every number below is indicative, not statistically tested.**

## Timeline (seconds from load start)
| t | event |
|---|---|
| 0-40 | normal operation |
| 40 | `r1` process killed (SIGKILL) |
| 80 | `r1` restarted; healthy again after 0.8 s |
| 120 | `r1` throttled by SIGSTOP/SIGCONT duty cycling (about 30% of CPU time) |
| 170 | throttle removed |
| 200 | load ends (stragglers drain until ~235 s) |

## Detection (metrics and alerts)
Prometheus and Grafana could not run here (no Docker daemon), so the alert rules in `deploy/alerts.yml` were **re-evaluated offline
in Python on the scraped `/metrics` counters (every 2 s)**, with the burn-rate windows scaled from 5 m / 1 h to 10 s / 30 s and the
`for:` clause not modelled. Dashboard-equivalent panels are rendered with matplotlib from the same data.

| fault | alert | first fire after fault onset (no breaker / breaker) |
|---|---|---|
| kill r1 | `ReplicaErrors` (any upstream error in 10 s) | 0.3 s / 0.3 s (limited by the 2 s scrape interval) |
| kill r1 | `SLOFastBurn` | **not a clean signal**: it was already firing at t=30-38 s in both runs, because the "healthy" phase at 1.0 req/s sits at the SLO knee (only 73-77% of requests met TTFT <= 2 s in that phase) |
| throttle r1 | `SLOFastBurn` (14.4x burn, 10 s and 30 s windows) | 18.7 s / 30.7 s |
| throttle r1 | `ReplicaErrors` | never fires: a throttled replica is slow, not erroring |

Take-aways: a hard failure is caught immediately by the error alert; a gray failure (slow replica) is caught only by the SLO burn alert,
tens of seconds later, and the error alert is blind to it. Because the baseline load already burns the budget, the SLO needs either a
lower load or a looser target (here: 2 s at 1.0 req/s is not a comfortable operating point; see ADR-002).

## Root cause (traces)
Gateway spans (`results/drill_<tag>/spans.jsonl`, OpenTelemetry JSON lines) carry `replica`, `ttft_s` and llama-server's own
`prompt_ms` / `predicted_ms`.
- **Kill window:** every upstream span with ERROR status belongs to `r1` (15 of 15 without the breaker, 10 of 10 with it).
- **Throttle window** (t = 125-170 s): mean TTFT on `r1` 15.3 s vs `r0` 0.63 s (breaker run: 11.6 s vs 0.65 s). llama-reported prefill time
  1683 ms vs 585 ms and decode time 8536 ms vs 1547 ms. Both stages are slow inside the replica, so the cause is replica compute
  (CPU starvation), not gateway queueing or the network.

## Recovery behaviour (routing and admission)
| phase | variant | error rate | p95 TTFT | share of requests sent to r1 |
|---|---|---|---|---|
| r1 killed (40-80 s) | no breaker | 51.7% (n=29) | 1.09 s (successes only) | 52% |
| r1 killed | circuit breaker (3 s cooldown) | 27.8% (n=36) | 1.57 s | 28% |
| after restart (85-120 s) | both | 0% | 1.18 s / 0.86 s | 49-50% |
| r1 throttled (120-170 s) | no breaker | 0% | 21.65 s | 50% |
| r1 throttled | circuit breaker | 0% | 17.88 s | 50% |
| after unthrottle (170-200 s) | no breaker / breaker | 0% | 12.7 s / 6.6 s (backlog draining) | 50% |
- **Routing, kill:** round-robin has no health awareness, so half of all requests went to the dead replica. The passive circuit breaker
  (trips on connection/read errors, 3 s cooldown, half-open probe afterwards) roughly halved the error rate (51.7% -> 27.8%) and
  the traffic sent to `r1`; the remainder is requests in flight at the kill plus one probe per cooldown. The two runs differ by
  only 29 vs 36 requests, so treat the improvement as suggestive.
- **Routing, throttle:** the breaker does nothing (no errors), so round-robin kept sending 50% of traffic to the slow replica;
  p95 TTFT was 17-22 s. Admission control was off in this drill; with it on, its estimator uses the *least* loaded replica, which
  would also not see a single slow replica. Detecting a slow replica needs latency-aware routing (e.g. outlier ejection on
  per-replica TTFT), which is **not implemented**.
- **Restart:** `r1` was healthy 0.8 s after the process start; traffic share returned to 49-50% in the next window in both variants.
- **After the throttle:** the queue backlog took ~45-65 s to clear (SLOFastBurn last fired at t=215 s with the breaker and 235 s without).

## What went well / what to fix (blameless)
- Went well: error alert and trace attributes pinpointed the killed replica within seconds; llama timings on spans separated
  "slow replica" from "queueing".
- To fix: (1) outlier ejection / latency-aware routing for gray failures; (2) retry-on-another-replica for connect errors that occur
  before the first byte, so a kill does not surface as client errors; (3) a quieter operating point so the SLO alert is meaningful;
  (4) run the real Prometheus rules (and Grafana) in compose, which is **not verified in this environment**.
