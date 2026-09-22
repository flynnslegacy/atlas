# Charge .env s'il existe (sans erreur s'il manque) et le passe à chaque recette.
-include .env
export

.PHONY: install test lint format bench run-core run-audio

install:
	uv sync --extra core --extra audio --extra dev

test:
	uv run pytest -v

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

bench:
	uv run python bench/bench.py

run-core:
	uv run uvicorn helios_core.hub:app --host 0.0.0.0 --port 8080

run-audio:
	uv run python -m helios_audio.client
