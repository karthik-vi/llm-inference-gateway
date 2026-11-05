PY ?= .venv/bin/python
.PHONY: setup download serve bench-baseline bench-ablation perfmodel eval test lint

setup:
	uv venv --python 3.11 .venv || python3 -m venv .venv
	uv pip install --python $(PY) -e ".[dev,bench]" || $(PY) -m pip install -e ".[dev,bench]"

download:  ## models + data (gitignored); implemented in Phase 1
	bash scripts/download.sh

serve:
	$(PY) -m gateway.main

bench-baseline:
	@echo "Phase 1 - not implemented yet" && false

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
