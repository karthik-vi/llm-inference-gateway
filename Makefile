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

bench-ablation:  ## ~1 h on 4 vCPU; each step restarts replicas. Reports land in results/ablation.csv (manual rows)
	bash scripts/download.sh
	RATES=1,2 bench/ablate.sh rr GATEWAY_ROUTING=round_robin
	RATES=1,2 bench/ablate.sh prefix GATEWAY_ROUTING=prefix
	RATES=2,3,4,6 bench/ablate.sh adm GATEWAY_ADMISSION=1
	RATES=1,2,3 WARM=1 bench/ablate.sh sem GATEWAY_SEMCACHE=1
	bench/quant.sh
	$(PY) -m bench.control_plane
	bench/cascade_ab.sh
	@echo "Summaries: python -m bench.report --tag <tag> --slo 2.0"

perfmodel:  ## predicted vs measured table (uses results/*.csv; `$(PY) -m perfmodel.micro` re-measures HW)
	$(PY) -m perfmodel.correlate
	$(PY) -m perfmodel.validate

eval:
	@echo "Phase 4 - not implemented yet" && false

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

test:
	$(PY) -m pytest -q
