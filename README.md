# NetAI

NetAI is a local-first framework for building LLM-powered workflows for network operations.

It gives you a reusable stack with:
- a chat UI
- an API + agent orchestration layer
- log ingestion and retrieval
- vector + analytical storage
- observability for latency, token usage, and spend

The goal is to make use cases like "answer questions about syslogs" or "help diagnose network issues" fast to implement and iterate.

## What It Does

- Natural language Q&A over network logs
- Evidence-backed answers from:
  - ClickHouse events
  - Qdrant template retrieval
- Agent-style chat with conversation history
- Streaming responses in the UI
- Metrics and dashboards for API/LLM usage

## Architecture At A Glance

```text
Vue UI (Vite)
    |
    v
FastAPI backend (agents/workflows)
    |                 \
    |                  -> SQLite (chat metadata, messages, tool calls, feedback)
    v
Retrieval layer
  - ClickHouse (events)
  - Qdrant (templates/embeddings)

Kafka -> Rust log_ingestor -> ClickHouse + Qdrant

Prometheus <- /metrics (backend)
Grafana <- Prometheus dashboards
Langfuse (optional tracing)
```

## Repository Structure

```text
.
├── backend/           # FastAPI app, workflows, prompts, retrieval, DB models/migrations
├── ui/                # Vue frontend
├── log_ingestor/      # Rust Kafka consumer + processing pipeline
├── monitoring/        # Prometheus + Grafana provisioning/dashboards
├── docker-compose.yaml
└── Makefile
```

## Prerequisites

- Docker + Docker Compose
- Python 3.13+
- `uv` (Python package manager/runner)
- Node.js 18+
- npm
- Rust toolchain (for `log_ingestor`)

## Quick Start (Local)

### 1) Start infrastructure

From repo root:

```bash
docker compose up -d
```

This starts:
- Zookeeper + Kafka
- Qdrant
- ClickHouse
- Prometheus
- Grafana (`http://localhost:3000`, `admin/admin`)

### 2) Configure backend environment

```bash
cd backend
cp .env.skeleton .env
```

Edit `backend/.env` and set at least:
- `PROJECT_NAME`
- `QDRANT_COLLECTION` (default: `syslogs`)
- one provider key:
  - `GEMINI_API_KEY` (if `LOG_QA_PROVIDER=gemini`)
  - or `OPENAI_API_KEY` (if `LOG_QA_PROVIDER=openai`)

### 3) Install backend dependencies and run migrations

```bash
cd backend
uv sync
uv run alembic upgrade head
```

### 4) Run backend API

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API base URL: `http://127.0.0.1:8000/api/v1`

### 5) Run frontend

In a second terminal:

```bash
cd ui
npm install
npm run dev
```

UI default dev URL: `http://localhost:5173`

### 6) Run log ingestor (optional but recommended)

In a third terminal:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml
```

This consumes Kafka syslog messages and writes processed outputs into ClickHouse + Qdrant.

### 7) Run CLI (optional)

In a fourth terminal:

```bash
cd backend
uv run python -m app.cli
```

## Common Commands

From repo root:

```bash
make help
make api
make api-prod
make ingestor
```

From `ui/`:

```bash
npm run dev
npm run build
npm run lint
```

## Key Configuration

### Backend (`backend/.env`)

Core:
- `API_V1_STR` (default `/api/v1`)
- `FRONTEND_HOST` (default `http://localhost:5173`)
- `SQLALCHEMY_URL` (default sqlite local file)

Retrieval/data:
- `CLICKHOUSE_URL`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`
- `QDRANT_URL`, `QDRANT_COLLECTION`

LLM:
- `LOG_QA_PROVIDER` (`gemini` or `openai`)
- `LOG_QA_MODEL`
- `GEMINI_API_KEY` / `OPENAI_API_KEY`
- `LLM_CONTEXT_WINDOW`

Observability:
- `LANGFUSE_ENABLED`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`
- token pricing env vars (`*_COST_PER_1M_TOKENS`) for spend metrics

### Frontend (`ui/.env.development`)

- `VITE_BASE_URL="http://127.0.0.1:8000/api/v1"`

## API Overview

Base path: `/api/v1`

Main routes:
- `POST /logs/ask` - log QA workflow
- `POST /agent/ask` - capability router workflow
- `POST /llm/conversation` - create conversation
- `GET /llm/conversations` - list conversations
- `GET /llm/conversation/{conversation_id}` - conversation details
- `POST /llm/conversation/{conversation_id}/message` - non-streaming message
- `POST /llm/conversation/{conversation_id}/message/stream` - streaming message
- `POST /llm/messages/{message_id}/feedback` - feedback on assistant answer

Metrics endpoint:
- `GET /metrics`

## Observability

- Prometheus scrapes backend metrics from `/metrics`
- Grafana dashboards are provisioned from `monitoring/grafana/dashboards`
- LLM traces can be sent to Langfuse when enabled
- In dev compose, Langfuse UI is available at `http://localhost:3002`

## Typical Local Flow

1. Start infra with Docker Compose.
2. Start backend API.
3. Start UI and open the Chat page.
4. Produce logs into Kafka topic `syslogs`.
5. Run `log_ingestor` so logs are indexed into ClickHouse/Qdrant.
6. Ask questions in UI or via `/api/v1/logs/ask`.

## Troubleshooting

- `No token provided for Gemini model`:
  - Set `GEMINI_API_KEY` or switch `LOG_QA_PROVIDER` to `openai` and set `OPENAI_API_KEY`.

- Empty/weak answers:
  - Verify ingestor is running.
  - Check Kafka topic has messages.
  - Check ClickHouse/Qdrant are reachable and populated.

- UI cannot reach API:
  - Confirm backend is on `:8000`.
  - Confirm `ui/.env.development` points to `/api/v1`.
  - Confirm CORS allows `http://localhost:5173`.

- Port conflicts:
  - `3000` is used by Grafana in `docker-compose.yaml`.
  - `3002` is used by Langfuse in `docker-compose.dev.yaml`.

## Current Caveats

- `make cli` currently points to `cli.py` at repo root, but the CLI entrypoint is `backend/app/cli.py`.
  - Use: `cd backend && uv run python -m app.cli`

- `backend/.env.skeleton` contains `GEMINI_API_KEY` twice.
  - Keep a single key in your actual `.env`.

## Roadmap (High-Level)

- Expand connectors and tool integrations (network systems, ticketing, SCM)
- Improve diagnosis workflows and capability routing
- Harden auth/SSO and production deployment profile
- Close the feedback loop by injecting summarized user feedback into prompt strategy





### Core Diagnostic & Fast Retrieval Tools

Here’s a practical list of tools we'll implement refactoring our zabbix_tools.py, grouped by use case.

#### 1. Host Discovery & Overview
- `get_hosts()` — List hosts with filters (by name, group, tags, status, maintenance). Include basic info like availability, interfaces, and last seen.
- `get_host_details(hostname_or_ip)` — Full host info + interfaces, macros, inventory, templates applied, tags.
- `get_host_interfaces(hostname_or_ip)` — Exactly as you mentioned: returns all interfaces (agent, SNMP, JMX, IPMI) with IP, port, type, and status. Very useful for connectivity diagnostics.
- `get_host_groups()` / `get_hosts_in_group(group)`

#### 2. Problems & Alerts (Most Important for Diagnostics)
- `get_problems()` — Active problems only, with filters: severity (High+), host/group, time since, unacknowledged, unsuppressed. Always expand hosts, triggers, and last event.
- `get_recent_problems(hours=24)` — Quick "what broke in the last day?"
- `get_host_problems(hostname_or_ip)` — All current + recent problems for a specific host.
- `get_trigger_problems(trigger)` — Problems linked to a specific trigger.

#### 3. Triggers & Root Cause
- `get_triggers(hostname_or_ip)` — Triggers for a host, with status (enabled/disabled), severity, last change, expression (expanded if possible).
- `get_trigger_details(trigger_id)` — Full expression, dependencies, tags, recovery info.

#### 4. Metrics & Historical Data (Trends)
- `get_latest_metrics_data(hostname_or_ip)` — Latest values for key items (CPU, memory, disk, etc.). Support item key patterns or tags.
- `get_metrics_history(item_id or key, hours=1..24, limit)` — Raw or aggregated history (avg, min, max). Crucial for "is it spiking?" questions.
- `get_host_metrics_summary(hostname_or_ip)` — High-level summary: top utilized resources, any items in error state.

#### 5. Events & History
- `get_events(hostname_or_ip or problem, hours=24)` — Full event log around a problem (including OK events).
- `get_audit_log(hours=24)` — What changed recently (config changes that might have caused issues).

#### 6. Infrastructure & Context
- `get_host_templates(hostname_or_ip)` — Which templates are linked (helps understand what is being monitored).
- `get_maintenance(hostname_or_ip)` — Is anything in maintenance? When does it end?
- `get_proxies()` — Proxy status and which hosts they handle (useful if agent/proxy communication is suspected).
- `get_zabbix_server_status()` — Overall Zabbix health (queue, alerts, performance).

#### 7. Convenience / AI-Friendly Tools
- `diagnose_host(hostname_or_ip)` — One-shot tool that returns: current problems, latest key metrics, interface status, recent events, and a short natural-language summary.
- `get_dashboard_snapshot(dashboard or "problems")` — Quick overview data.

### Implementation Tips for an Effective Diagnostics

- **Smart defaults** — Most tools should default to "active/recent/important only" (e.g., problems with severity ≥ Average, last 24h).
- **Rich output** — Always use `selectHosts`, `selectItems`, `selectTriggers`, `selectLastEvent`, `expandDescription`, etc., so the AI gets usable context without extra calls.
- **Pagination & limits** — Add sensible limits + sorting (by severity, clock descending) to avoid overwhelming the context window.
- **Tool search** — If you have many tools (>50), enable a `search_tools()` + `call_tool(name, params)` pattern so the AI can discover what it needs without loading everything.
- **Error handling** — Tools should return clear messages when something is not found, suppressed, or in maintenance.


### After finishing

After this is finished, update the Zabbix agent ZABBIX_SPECIALIST_PROMPT and the agent description to explain to the agent what capabilities it has, and also tell it to setup a plan before acting.