# Ansible Deployment (Bare-Metal Ubuntu)

This folder deploys NetAI to Ubuntu hosts without Docker.

## Structure

- `playbooks/deploy.yml`: shared deployment logic
- `playbooks/deploy-dev.yml`: deploys branch `dev`
- `playbooks/deploy-staging.yml`: deploys branch `staging`
- `playbooks/deploy-prod.yml`: deploys branch `main`
- `roles/base`: OS packages (`git`, `nodejs`, `nginx`, etc.)
- `roles/datastores`: installs/configures `ClickHouse`, `Qdrant`, and `Redis`
- `roles/netai`: app deploy, build, systemd services, nginx site
- `inventories/*`: optional local examples (Tower inventory can be used instead)

## What This Deploys

- Creates a deploy user (`netai`) and install path `/opt/netai/current`
- Clones/pulls the selected Git branch
- Installs and configures:
  - `ClickHouse` (database + user)
  - `Redis`
  - `Qdrant` (built from source, managed by systemd)
- Installs Python runtime via `uv` (Python 3.13), then runs backend migrations
- Builds frontend static assets
- Builds `log_ingestor` release binary (optional)
- Configures and starts:
  - `netai-backend` (systemd)
  - `netai-log-ingestor` (systemd, optional)
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
  CLICKHOUSE_URL: http://127.0.0.1:8123
  CLICKHOUSE_DB: netops
  CLICKHOUSE_USER: admin
  CLICKHOUSE_PASSWORD: "<set-me>"
  QDRANT_URL: http://127.0.0.1:6333
  QDRANT_COLLECTION: syslogs
  LOG_QA_PROVIDER: gemini
  LOG_QA_MODEL: gemini-2.5-flash
  GEMINI_API_KEY: "<set-me>"
  OPENAI_API_KEY: ""

# Datastores role vars (optional overrides)
netai_clickhouse_db: netops
netai_clickhouse_user: admin
netai_clickhouse_password: "<set-me>"
netai_redis_password: "<optional>"
netai_qdrant_version: v1.16.3
```

Optional overrides:

```yaml
netai_server_name: netai.example.com
netai_backend_port: 8000
netai_enable_log_ingestor: true
netai_ui_env:
  VITE_BASE_URL: /api/v1
```

## Local CLI Run (optional)

```bash
cd ansible
ansible-playbook -i inventories/dev/hosts.yml playbooks/deploy-dev.yml
```

Use `staging` or `prod` inventory/playbook as needed.
