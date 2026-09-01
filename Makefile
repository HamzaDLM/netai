.PHONY: help cli api api-prod ingestor syslog-rust-build syslog-binaries syslog-ingestor-binary syslog-mcp-binary check-syslog-build-arch docker-up docker-rebuild docker-reset docker-dev-up docker-dev-rebuild docker-dev-down

SYSLOG_BUILD_ARCH_RAW := $(shell uname -m)
SYSLOG_BUILD_ARCH := $(if $(filter x86_64,$(SYSLOG_BUILD_ARCH_RAW)),amd64,$(if $(filter aarch64 arm64,$(SYSLOG_BUILD_ARCH_RAW)),arm64,))
SYSLOG_ROLE_FILES := ansible/roles/syslog_stack/files
SYSLOG_RELEASE_DIR := log_ingestor/target/release

help:
	@echo "Available targets:"
	@echo "  make cli       - Run interactive Python CLI"
	@echo "  make api       - Run FastAPI with uvicorn (reload, :8000)"
	@echo "  make api-prod  - Run FastAPI with uvicorn (no reload, :8000)"
	@echo "  make ingestor  - Run Rust log_ingestor (cargo run)"
	@echo "  make syslog-binaries        - Build and stage both native syslog binaries"
	@echo "  make syslog-ingestor-binary - Build and stage the native ingestor binary"
	@echo "  make syslog-mcp-binary      - Build and stage the native MCP binary"
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

check-syslog-build-arch:
	@test -n "$(SYSLOG_BUILD_ARCH)" || { echo "Unsupported build architecture: $(SYSLOG_BUILD_ARCH_RAW)"; exit 1; }

syslog-rust-build: check-syslog-build-arch
	cargo build --locked --release --bins --manifest-path log_ingestor/Cargo.toml

syslog-ingestor-binary: syslog-rust-build
	install -d "$(SYSLOG_ROLE_FILES)"
	install -m 0755 "$(SYSLOG_RELEASE_DIR)/log_ingestor" "$(SYSLOG_ROLE_FILES)/netai-log-ingestor-$(SYSLOG_BUILD_ARCH)"
	sha256sum "$(SYSLOG_ROLE_FILES)/netai-log-ingestor-$(SYSLOG_BUILD_ARCH)"

syslog-mcp-binary: syslog-rust-build
	install -d "$(SYSLOG_ROLE_FILES)"
	install -m 0755 "$(SYSLOG_RELEASE_DIR)/syslog_mcp" "$(SYSLOG_ROLE_FILES)/netai-syslog-mcp-$(SYSLOG_BUILD_ARCH)"
	sha256sum "$(SYSLOG_ROLE_FILES)/netai-syslog-mcp-$(SYSLOG_BUILD_ARCH)"

syslog-binaries: syslog-ingestor-binary syslog-mcp-binary

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
