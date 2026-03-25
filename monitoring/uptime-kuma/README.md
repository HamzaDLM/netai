# Uptime Kuma Monitors For NetAI

Open Uptime Kuma at `http://localhost:3001` and create monitors with these targets.

Recommended monitors:

- `backend-api` (HTTP): `http://backend:8000/metrics`
- `ui` (HTTP): `http://ui/`
- `clickhouse-http` (HTTP): `http://clickhouse:8123/ping`
- `qdrant-ready` (HTTP): `http://qdrant:6333/readyz`
- `kafka-broker` (TCP): `kafka:29092`
- `zookeeper` (TCP): `zookeeper:2181`
- `prometheus` (HTTP): `http://prometheus:9090/-/healthy`
- `grafana` (HTTP): `http://grafana:3000/api/health`

Notes:

- `log_ingestor` is best monitored as a Docker monitor from Uptime Kuma because it has no HTTP endpoint.
- If you want Docker-type monitors, mount Docker socket into `uptime_kuma` (optional).
- Suggested polling interval: `30s` for HTTP/TCP checks.
