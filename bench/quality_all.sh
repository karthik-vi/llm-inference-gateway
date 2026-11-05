#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bench/quality.sh q05q8 GATEWAY_CONFIG=config_eval_q05q8.yaml
bench/quality.sh q05f16 GATEWAY_CONFIG=config_eval_q05f16.yaml
bench/quality.sh q05q4_sem GATEWAY_CONFIG=config_eval_q05q4.yaml GATEWAY_SEMCACHE=1 WARM=1
bench/quality.sh q15q4 GATEWAY_CONFIG=config_eval_q15q4.yaml
bench/quality.sh q15q8 GATEWAY_CONFIG=config_eval_q15q8.yaml
