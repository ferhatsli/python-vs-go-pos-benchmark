SHELL := /usr/bin/env bash
PROFILE ?= D1

.PHONY: test-harness preflight verify-isolation freeze-source validate-contracts compose-up compose-down db-init db-check db-seed db-reset db-fingerprint db-plans

test-harness:
	pytest -q tests

preflight:
	bash scripts/preflight.sh

verify-isolation:
	bash scripts/verify_isolation.sh

freeze-source:
	bash scripts/freeze_source.sh

validate-contracts:
	python3 scripts/validate_contracts.py

compose-up:
	docker compose up -d postgres redis

db-init:
	docker compose exec -T postgres psql -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/003_extensions.sql
	docker compose exec -T postgres psql -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/001_schema.sql
	docker compose exec -T postgres psql -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/002_indexes.sql

db-check:
	docker compose exec -T postgres psql -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/checks/invariants.sql

db-seed:
	python3 db/seed/seed.py --profile $(PROFILE)

db-reset:
	python3 db/reset/reset.py --profile $(PROFILE)

db-fingerprint:
	python3 db/seed/seed.py --profile $(PROFILE) --fingerprint-only

db-plans:
	docker compose exec -T postgres psql -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/checks/query_plans.sql

compose-down:
	docker compose down
