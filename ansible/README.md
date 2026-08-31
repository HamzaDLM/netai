# Ansible Deployment (Bare-Metal Ubuntu)

This folder deploys NetAI to Ubuntu hosts without Docker.

## Structure

- `playbooks/deploy.yml`: shared deployment logic
- `playbooks/deploy-dev.yml`: deploys branch `dev`
- `playbooks/deploy-staging.yml`: deploys branch `staging`
- `playbooks/deploy-prod.yml`: deploys branch `main`
- `roles/base`: OS packages (`git`, `nodejs`, `nginx`, etc.)
- `roles/datastores`: installs/configures Qdrant
- `roles/netai`: app deploy, build, systemd services, nginx site
- `roles/syslog_stack`: deploys ClickHouse, Redis, the syslog ingestor, and the
  read-only syslog MCP service as one operational unit
- `inventories/*`: optional local examples (Tower inventory can be used instead)

## What This Deploys

- Creates a deploy user (`netai`) and install path `/opt/netai/current`
- Clones/pulls the selected Git branch
- Installs and configures Qdrant (built from source, managed by systemd)
- Deploys the complete syslog intelligence stack from one role:
  - a pinned official ClickHouse static binary, database, and application user
  - Redis
  - the NetAI syslog ingestor binary
  - the read-only NetAI syslog MCP binary
- Installs Python runtime via `uv` (Python 3.13), then runs backend migrations
- Builds frontend static assets
- Builds the syslog ingestion and syslog MCP release binaries (optional)
- Configures and starts:
  - `netai-backend` (systemd)
  - `netai-mcp-servers` (systemd, optional; runs all configured MCP HTTP servers in one process)
  - `netai-log-ingestor` (systemd, optional)
  - `netai-syslog-mcp` (systemd, optional; read-only ClickHouse query boundary)
  - `nginx` (serves UI + proxies `/api/` to backend)

## Tower/AWX Usage

1. Create one Job Template per environment:
   - Dev: `playbooks/deploy-dev.yml`
   - Staging: `playbooks/deploy-staging.yml`
   - Prod: `playbooks/deploy-prod.yml`
2. Keep host/IP, SSH user, password/key in Tower inventory + credentials.
3. Set secrets/overrides in Tower vars (Inventory vars, Job Template vars, or credential injection).

### Minimum vars to set in Tower

```yaml
netai_git_repo: https://github.com/<your-org>/<your-repo>.git

netai_backend_env:
  PROJECT_NAME: NetAI
  SYSLOG_MCP_URL: http://127.0.0.1:8010/mcp
  SYSLOG_MCP_TOKEN: "<set-me>"
  GEMINI_MODEL: gemini-2.5-flash
  GEMINI_API_KEY: "<set-me>"
  TOOLS_USE_MOCK_DATA: "false"
  MCP_CONSUMER_TOKEN: "<set-me>"

netai_log_ingestor_env:
  KAFKA_BROKERS: 127.0.0.1:9092
  CLICKHOUSE_URL: http://127.0.0.1:8123
  CLICKHOUSE_PASSWORD: "<set-me>"
  INGEST_MAX_IN_FLIGHT: "256"
  METRICS_BIND: 127.0.0.1:9898
  SYSLOG_MCP_BIND: 127.0.0.1:8010
  SYSLOG_MCP_TOKEN: "<set-me>"
  REDIS_URL: redis://127.0.0.1:6379/
  VENDOR_LOOKUP_URL: ""

# Syslog stack role vars (optional overrides)
netai_clickhouse_version: "26.3.17.110"
netai_clickhouse_db: netops
netai_clickhouse_user: admin
netai_clickhouse_password: "<set-me>"
netai_redis_password: "<optional>"

# Datastores role vars (optional overrides)
netai_qdrant_version: v1.16.3
```

Optional overrides:

```yaml
netai_server_name: netai.example.com
netai_backend_port: 8000
netai_syslog_stack_enabled: true
netai_clickhouse_enabled: true
netai_redis_enabled: true
netai_enable_log_ingestor: true
netai_enable_syslog_mcp: true
netai_restart_backend_with_syslog_mcp: true
netai_enable_mcp_servers: true
netai_log_ingestor_cpu_quota: "100%"
netai_log_ingestor_memory_max: 1G
netai_syslog_mcp_cpu_quota: "50%"
netai_syslog_mcp_memory_max: 512M
netai_ui_env:
  VITE_BASE_URL: /api/v1
```

The `syslog_stack` role pins and checksum-verifies the ClickHouse archive instead
of using Ubuntu's often outdated ClickHouse package. Override
`netai_clickhouse_version`, `netai_clickhouse_download_url`, and
`netai_clickhouse_checksum_url` together when using an internal artifact mirror.
For a host migrating from package-managed ClickHouse, set
`netai_clickhouse_remove_distribution_packages: true` to remove the legacy
packages without purging their data after the static archive is available.

The log ingestor's systemd unit also applies configurable CPU, memory, and task limits.
Prometheus-format ingestion and process metrics are available at `METRICS_BIND/metrics`.

## Local CLI Run (optional)

```bash
cd ansible
ansible-playbook -i inventories/dev/hosts.yml playbooks/deploy-dev.yml
```

Use `staging` or `prod` inventory/playbook as needed.
