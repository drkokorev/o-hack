PY ?= .venv/bin/python

.PHONY: install test run up down climate hotels images llm-check eval simulate

install:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt -r requirements-voice.txt

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

hotels:
	$(PY) -m tools.build_hotels

images:
	$(PY) -m tools.build_images

llm-check:
	$(PY) -m tools.llm_check

eval:
	$(PY) -m eval.compare_models --models rules --output eval/guided_report.json

simulate:
	$(PY) -m eval.simulate
