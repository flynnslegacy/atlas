# Charge .env s'il existe (sans erreur s'il manque) et le passe à chaque recette.
-include .env
export

.PHONY: install test test-swift lint format bench run-core run-audio

install:
	uv sync --extra core --extra audio --extra dev

test:
	uv run pytest -v

test-swift:
	swiftc -sanitize=thread src/atlas_aec/Sources/atlas-aec/Tampons.swift tests/aec/tampons/main.swift -o "$$TMPDIR/harnais" && "$$TMPDIR/harnais"

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

bench:
	uv run python bench/bench.py

run-core:
	uv run uvicorn atlas_core.hub:app --host 0.0.0.0 --port 8080

run-audio:
	uv run python -m atlas_audio.client
