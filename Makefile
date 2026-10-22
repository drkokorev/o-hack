PY ?= .venv/bin/python
PORT ?= 8000
DATA ?= data/

.PHONY: install test web cli eval llm-check inspect

install:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt

test:
	$(PY) -m pytest -q

web:
	PORT=$(PORT) $(PY) -m apps.web

cli:
	$(PY) -m apps.cli --debug

eval:
	$(PY) -m eval.run
	$(PY) -m eval.run --cases eval/cases_holdout.json --out eval/report_holdout

llm-check:
	$(PY) -m tools.llm_check

inspect:
	$(PY) -m tools.inspect_data $(DATA) --out $(DATA)/profile.md
