PG_URL ?= postgresql+psycopg2://pmo:pmo@localhost:5432/source

.PHONY: install up down sim-init sim-advance sim-status sim-init-sqlite ingest ingest-full ingest-status test lint

install:            ## install dependencies with uv
	uv sync

up:                 ## start the source Postgres database
	docker compose up -d --wait

down:
	docker compose down

sim-init: up        ## backfill the fictional company from 2024-07-01 to today (Postgres)
	SOURCE_DB_URL=$(PG_URL) uv run python -m simulator init

sim-advance:        ## move the company forward one week
	SOURCE_DB_URL=$(PG_URL) uv run python -m simulator advance --days 7

sim-status:
	SOURCE_DB_URL=$(PG_URL) uv run python -m simulator status

sim-init-sqlite:    ## same as sim-init but no Docker needed (data/source.db)
	uv run python -m simulator init

ingest:             ## load changed rows from the source DB + new tracker weeks into data/warehouse.duckdb
	SOURCE_DB_URL=$(PG_URL) uv run python -m ingestion run

ingest-full:        ## drop the raw layer and reload everything
	SOURCE_DB_URL=$(PG_URL) uv run python -m ingestion run --full-refresh

ingest-status:
	uv run python -m ingestion status

test:
	uv run pytest -q

lint:
	uv run ruff check .
