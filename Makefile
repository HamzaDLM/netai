.PHONY: help cli api api-prod ingestor

help:
	@echo "Available targets:"
	@echo "  make cli       - Run interactive Python CLI"
	@echo "  make api       - Run FastAPI with uvicorn (reload, :8000)"
	@echo "  make api-prod  - Run FastAPI with uvicorn (no reload, :8000)"
	@echo "  make ingestor  - Run Rust log_ingestor (cargo run)"

cli:
	uv run python cli.py

api:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

api-prod:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

ingestor:
	cargo run --manifest-path log_ingestor/Cargo.toml
