PY ?= .venv/bin/python
.PHONY: setup download serve bench-baseline bench-ablation perfmodel eval test lint

setup:
	uv venv --python 3.11 .venv || python3 -m venv .venv
	uv pip install --python $(PY) -e ".[dev,bench,cache]" || $(PY) -m pip install -e ".[dev,bench,cache]"

download:  ## models + data (gitignored); implemented in Phase 1
	bash scripts/download.sh

serve:
	$(PY) -m gateway.main

SLO ?= 2.0
bench-baseline:  ## ~11 min on 4 vCPU: 2 replicas, gateway, sweep, report
	bash scripts/replicas.sh start
	$(PY) -m workloads.trace 400
	(GATEWAY_CONFIG=config.yaml $(PY) -m gateway.main & echo $$! > logs/gw.pid); sleep 3
	$(PY) -m bench.sweep --tag baseline --rates 0.5,1,2,3,4,6
	$(PY) -m bench.report --tag baseline --slo $(SLO)
	kill `cat logs/gw.pid`; bash scripts/replicas.sh stop

bench-ablation:
	@echo "Phase 2 - not implemented yet" && false

perfmodel:
	@echo "Phase 3 - not implemented yet" && false

eval:
	@echo "Phase 4 - not implemented yet" && false

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

test:
	$(PY) -m pytest -q
