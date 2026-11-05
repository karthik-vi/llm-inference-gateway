#!/usr/bin/env bash
# Usage: bench/ablate.sh <tag> <env assignments...>   e.g. bench/ablate.sh prefix GATEWAY_ROUTING=prefix
# Fresh replicas per config (so KV caches don't carry over), same trace + seeds, rates from $RATES.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}; TAG=$1; shift
bash scripts/replicas.sh stop; sleep 2; bash scripts/replicas.sh start >/dev/null
env "$@" $PY -m gateway.main > logs/gateway_$TAG.log 2>&1 & GW=$!
sleep 3
$PY -m bench.sweep --tag "$TAG" --rates "${RATES:-1,2}" --duration "${DURATION:-60}"
kill $GW; bash scripts/replicas.sh stop
