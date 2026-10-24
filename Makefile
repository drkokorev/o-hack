PY ?= .venv/bin/python

.PHONY: install test run up down climate llm-check eval simulate

install:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt

test:
	$(PY) -m pytest -q

run:
	$(PY) -m apps.web

up:
	docker compose up --build

down:
	docker compose down

climate:
	$(PY) -m tools.build_climate

llm-check:
	$(PY) -m tools.llm_check

eval:
	$(PY) -m eval.run

simulate:
	$(PY) -m eval.simulate
