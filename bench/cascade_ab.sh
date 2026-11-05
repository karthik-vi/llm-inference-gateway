#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export RATES=${RATES:-0.5,1}
bench/ablate.sh large GATEWAY_CONFIG=config_large.yaml
bench/ablate.sh casc_rule GATEWAY_CONFIG=config_cascade.yaml GATEWAY_CASCADE=rule
bench/ablate.sh casc_llm GATEWAY_CONFIG=config_cascade.yaml GATEWAY_CASCADE=llm
