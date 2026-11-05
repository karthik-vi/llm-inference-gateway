from prometheus_client import Counter, Gauge, Histogram

REQS = Counter("gw_requests_total", "Requests", ["replica", "status"])
TTFT = Histogram(
    "gw_ttft_seconds", "Time to first token", ["replica"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)
ITL = Histogram(
    "gw_itl_seconds", "Inter-token latency", ["replica"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
ERRORS = Counter("gw_errors_total", "Errors", ["replica", "kind"])
REJECTED = Counter("gw_rejected_total", "Requests rejected by admission control")
CACHE = Counter("gw_semcache_total", "Semantic cache lookups", ["result"])
CASCADE = Counter("gw_cascade_total", "Cascade decisions", ["tier"])
GOODPUT = Counter("gw_goodput_total", "Requests whose TTFT met the SLO")
INFLIGHT = Gauge("gw_inflight", "In-flight requests per replica", ["replica"])
REPLICA_DOWN = Gauge("gw_replica_down", "1 while the circuit breaker holds a replica out", ["replica"])
