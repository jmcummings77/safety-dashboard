install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pre-commit install

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

test:
	.venv/bin/pytest --cov --cov-report=term-missing

build:
	.venv/bin/python pipeline/build.py

refresh:
	.venv/bin/python pipeline/build.py --refresh

serve:
	python3 -m http.server 8765 --directory site

.PHONY: install lint format test build refresh serve
