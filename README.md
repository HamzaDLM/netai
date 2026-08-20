# NetAI

NetAI is a network-infrastructure assistant built with FastAPI, Haystack 3, and
Vue. A single Haystack Agent owns reasoning and tool execution; the backend adds
conversation persistence, authentication boundaries, live UI artifacts, and
infrastructure client lifecycle.

## Runtime architecture

```text
Vue chat UI
     |
FastAPI (HTTP, SSE, auth, persistence)
     |
NetAIService
     |
Haystack Agent.run_async()
     |
SearchableToolset -- loads relevant tools on demand
     |
     +-- Zabbix       (pyzabbix)
     +-- SuzieQ       (shared async HTTP)
     +-- ServiceNow   (shared async HTTP)
     +-- ClickHouse   (shared async HTTP)
     +-- Bitbucket    (local git CLI)
     +-- topology and safe diagnostic tools
     `-- Infrahub     (optional external MCP adapter)
```

The application does not call its own tools through MCP. Local tools are normal
Haystack `Tool` objects used directly by the Agent. MCP remains an external
protocol boundary: Infrahub is consumed as an optional remote toolset, and the
Zabbix MCP server exposes the same underlying Haystack tools to external clients.

The separate Rust log ingestor consumes Kafka and writes ClickHouse events.
NetAI reads recent host syslogs directly from ClickHouse; the repository's
Qdrant code and service remain isolated to ingestion experiments/legacy paths.

## Repository structure

```text
backend/app/
  agents/netai.py              # Agent prompt, state, and hooks
  services/netai.py            # lifecycle-owned application service
  services/chat_agent.py       # conversation prompt and SSE application flow
  tools/registry.py             # single runtime tool/catalogue source
  infrastructure/clients.py     # shared async HTTP pools and external spans
  mcp/                          # external MCP client/server adapters
  api/                          # FastAPI routes, schemas, and persistence
ui/                             # Vue frontend and inline visual components
log_ingestor/                   # Rust Kafka -> ClickHouse pipeline
monitoring/                     # Prometheus, Grafana, and Langfuse dev services
```

## Requirements

- Python 3.13 and `uv`
- Node.js and npm
- Docker Compose for local infrastructure
- Rust only when developing the log ingestor

## Local setup

```bash
docker compose up -d

cd backend
cp .env.skeleton .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Set at least `PROJECT_NAME`, `GEMINI_MODEL`, and `GEMINI_API_KEY` in
`backend/.env`. In another terminal:

```bash
cd ui
npm install
npm run dev
```

The API is available at `http://127.0.0.1:8000/api/v1`, and the development UI
defaults to `http://localhost:5173`.

## Configuration

Core:

- `SQLALCHEMY_URL`, `FRONTEND_HOST`, `BACKEND_CORS_ORIGINS`
- `GEMINI_MODEL`, `GEMINI_API_KEY`, `LLM_CONTEXT_WINDOW`
- `TOOLS_USE_MOCK_DATA` (defaults to `true`)

Connectors:

- Zabbix: `ZABBIX_ENABLED`, `ZABBIX_API_URL`, `ZABBIX_API_TOKEN`
- SuzieQ: `SUZIEQ_ENABLED`, `SUZIEQ_API_URL`, `SUZIEQ_API_TOKEN`,
  `SUZIEQ_VERIFY_TLS`
- ServiceNow: `SERVICENOW_ENABLED`, `SERVICENOW_INSTANCE_URL`, and bearer-token
  or username/password credentials
- Bitbucket: `BITBUCKET_ENABLED`, `BITBUCKET_URL`, `BITBUCKET_CLONE_DIR`
- ClickHouse: `CLICKHOUSE_URL`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`,
  `CLICKHOUSE_PASSWORD`
- Infrahub: `INFRAHUB_MCP_URL`, `INFRAHUB_MCP_TOKEN`,
  `INFRAHUB_MCP_TIMEOUT_SECONDS`

Optional tracing can target any OTLP/HTTP backend with
`OTEL_TRACING_ENABLED`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, and
`OTEL_EXPORTER_OTLP_TRACES_HEADERS`. Langfuse remains supported through its OTLP
endpoint using `LANGFUSE_*`; the Langfuse Python SDK is not required. Prompt and
tool content tracing is disabled by default and must be explicitly enabled with
`HAYSTACK_CONTENT_TRACING_ENABLED=true`.

## API and streaming

Primary routes:

- `POST /api/v1/agent/ask`
- `POST /api/v1/llm/conversation`
- `GET /api/v1/llm/conversations`
- `POST /api/v1/llm/conversation/{id}/message`
- `POST /api/v1/llm/conversation/{id}/message/stream`
- `POST /api/v1/llm/messages/{id}/feedback`
- `GET /metrics`

The streaming endpoint forwards native generator chunks and live tool/artifact
events. Visual payloads such as topology, configuration diffs, ping,
traceroute, and latency charts appear at the tool-call position rather than as
post-processed answer blocks.

## MCP

Run the example external Zabbix MCP adapter with:

```bash
cd backend
uv run mcp-zabbix-server --host 127.0.0.1 --port 8030
```

Infrahub discovery is lazy and failure-isolated. An unavailable Infrahub server
does not prevent startup or unrelated Agent requests.

## Verification

```bash
cd backend
uv run ruff check app tests
uv run mypy app
uv run pytest -q

cd ../ui
npm run build
```

## Known boundary

Authentication is still a development placeholder that resolves every request
to the demo administrator. Replace `app/core/security.py` with the production
SSO implementation before exposing NetAI outside a trusted environment.
