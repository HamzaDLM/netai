.PHONY: help cli api api-prod ingestor docker-up docker-rebuild docker-reset docker-dev-up docker-dev-rebuild docker-dev-down

help:
	@echo "Available targets:"
	@echo "  make cli       - Run interactive Python CLI"
	@echo "  make api       - Run FastAPI with uvicorn (reload, :8000)"
	@echo "  make api-prod  - Run FastAPI with uvicorn (no reload, :8000)"
	@echo "  make ingestor  - Run Rust log_ingestor (cargo run)"
	@echo "  make docker-up      - Start docker compose stack"
	@echo "  make docker-rebuild - Rebuild images (no cache) and recreate containers"
	@echo "  make docker-reset   - Full reset (remove containers + volumes), then rebuild"
	@echo "  make docker-dev-up      - Start stateless dev compose stack"
	@echo "  make docker-dev-rebuild - Stateless dev no-cache rebuild + recreate"
	@echo "  make docker-dev-down    - Stop and remove stateless dev stack"

cli:
	uv run python cli.py

api:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

api-prod:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

ingestor:
	cargo run --manifest-path log_ingestor/Cargo.toml

docker-up:
	docker compose up

docker-rebuild:
	docker compose build --no-cache
	docker compose up --force-recreate

docker-reset:
	docker compose down --volumes --remove-orphans
	docker compose build --no-cache
	docker compose up --force-recreate

docker-dev-up:
	docker compose -f docker-compose.dev.yaml up --build --force-recreate --renew-anon-volumes

docker-dev-rebuild:
	docker compose -f docker-compose.dev.yaml build --no-cache
	docker compose -f docker-compose.dev.yaml up --force-recreate --renew-anon-volumes

docker-dev-down:
	docker compose -f docker-compose.dev.yaml down --remove-orphans
