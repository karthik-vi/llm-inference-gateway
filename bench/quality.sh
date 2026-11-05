#!/usr/bin/env bash
# Usage: bench/quality.sh <tag> <env assignments...>   e.g. bench/quality.sh q05q4 GATEWAY_CONFIG=config_eval_q05q4.yaml
# Fresh replicas + gateway per config, then the agent eval (results/eval_<tag>.json).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}; TAG=$1; shift
for kv in "$@"; do export "$kv"; done
bash scripts/replicas.sh stop; sleep 2; bash scripts/replicas.sh start >/dev/null
$PY -m gateway.main > logs/gateway_q_$TAG.log 2>&1 & GW=$!
sleep 12
[ -n "${WARM:-}" ] && $PY -m bench.warm_cache
$PY -m eval.run --tag "$TAG" --workers "${WORKERS:-2}" | tee logs/eval_$TAG.log
curl -s http://127.0.0.1:8080/metrics | grep -E "^gw_(semcache|cascade|rejected)_total" > logs/metrics_$TAG.txt || true
kill $GW; bash scripts/replicas.sh stop
