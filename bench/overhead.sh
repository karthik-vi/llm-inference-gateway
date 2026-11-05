#!/usr/bin/env bash
# Gateway added latency: client->mock direct vs client->gateway->mock; py-spy flamegraph of the gateway.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}; RATE=${RATE:-40}; DUR=${DUR:-20}
$PY bench/mock_upstream.py 9201 & M1=$!; $PY bench/mock_upstream.py 9202 & M2=$!
GATEWAY_CONFIG=config_mock.yaml $PY -m gateway.main & GW=$!
sleep 3
run() { $PY -m workloads.loadgen --url "$1" --rate $RATE --duration $DUR --think 0 --timeout 20 --out "$2" > "$3"; }
run http://127.0.0.1:9201 logs/oh_direct.csv logs/oh_direct.json
(.venv/bin/py-spy record -p $GW -d $((DUR+2)) -f flamegraph -o results/gateway_flamegraph.svg > logs/pyspy.log 2>&1 || echo "py-spy failed" >> logs/pyspy.log) &
run http://127.0.0.1:8081 logs/oh_gateway.csv logs/oh_gateway.json
wait %4 2>/dev/null || true
kill $M1 $M2 $GW 2>/dev/null || true
