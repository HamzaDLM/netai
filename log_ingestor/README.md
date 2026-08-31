# log_ingestor

Standalone Rust network-device syslog intelligence service. Its ingestion process parses Kafka
syslogs into ClickHouse; its independently runnable MCP process
owns all read access so NetAI never needs ClickHouse SQL or credentials.

## Runtime layout

```text
Kafka -> log_ingestor -> ClickHouse <- syslog_mcp <- NetAI
```

Both binaries share typed storage and query code but restart and scale independently.

## Current Flow

1. Consume JSON messages from Kafka topic (`KAFKA_TOPIC`, default `syslogs`).
2. Parse each message into:
   - `syslog_timestamp`
   - `syslog_hostname`
   - `syslog_message`
   - optional `vendor`
3. Drop messages containing any configured ignored syslog text.
4. Run lightweight vendor-aware parsing:
   - detect vendor from explicit `vendor` when present, otherwise heuristics
   - extract metadata where possible (`facility`, `severity`, `event_code`)
5. Write the original message and parsed metadata to ClickHouse table `syslog_events`.

The service deliberately does not normalize or template message text. Replacing diagnostic values
such as IP addresses, interfaces, and counters made the evidence less useful without providing a
runtime feature. Existing derived columns are removed by the startup schema migration.

## Environment Variables

Copy the skeleton if you want a dedicated local config:

```bash
cp log_ingestor/.env.skeleton log_ingestor/.env
```

### Kafka
- `KAFKA_BROKERS` (default: `localhost:9092`)
- `KAFKA_TOPIC` (default: `syslogs`)
- `KAFKA_GROUP_ID` (default: `log-ingestor`)

### ClickHouse

ClickHouse 19.6 or newer is required because the event table uses a table-level
TTL. Docker Compose pins ClickHouse 24.8; Ansible installs the current official
LTS packages rather than Ubuntu's obsolete distribution package.
- `CLICKHOUSE_URL` (default: `http://localhost:8123`)
- `CLICKHOUSE_DB` (default: `netops`)
- `CLICKHOUSE_USER` (default: `admin`)
- `CLICKHOUSE_PASSWORD` (default: `admin`)
- `CLICKHOUSE_RETENTION_DAYS` (default: `30`)
- `CLICKHOUSE_BATCH_SIZE` (default: `1000`)
- `CLICKHOUSE_FLUSH_INTERVAL_MS` (default: `100`)
- `CLICKHOUSE_INSERT_QUEUE_CAPACITY` (default: `20000`)
- `CLICKHOUSE_INSERT_MAX_RETRIES` (default: `5`; the initial attempt is additional)
- `CLICKHOUSE_INSERT_RETRY_BACKOFF_MS` (default: `250`; exponential, capped at 30 seconds)
- `CLICKHOUSE_INSERT_TIMEOUT_SECS` (default: `10` per attempt)
- `INGEST_MAX_IN_FLIGHT` (default: `256`; bounds records processing or awaiting persistence)
- `KAFKA_LAG_POLL_INTERVAL_SECS` (default: `15`)
- `METRICS_BIND` (default: `0.0.0.0:9898`; serves `/metrics`)
- `IGNORED_SYSLOG_TEXTS` (optional comma/newline-separated substrings; defaults include `vfork couldn't find enough ressources` and `vfork couldn't find enough resources`)

### Syslog MCP/query service

- `SYSLOG_MCP_BIND` (default: `0.0.0.0:8010`)
- `SYSLOG_MCP_ALLOWED_HOSTS` (comma-separated MCP Host-header allowlist)
- `SYSLOG_MCP_TOKEN` (optional bearer token; configure it outside local development)
- `SYSLOG_QUERY_DEFAULT_WINDOW_SECS` (default: `3600`)
- `SYSLOG_QUERY_MAX_WINDOW_SECS` (default: `604800`, seven days)
- `SYSLOG_QUERY_MAX_RESULTS` (default: `200`)
- `SYSLOG_QUERY_TIMEOUT_SECS` (default: `8`)

The MCP service exposes only typed, bounded, read-only operations:

- `syslog_get_device_events`
- `syslog_get_severity_summary`
- `syslog_get_event_summary`

Raw event results default to 20 rows. Their MCP representation contains only the timestamp,
original message, and available parsed metadata; storage-only identifiers and repeated host/vendor
fields are not sent for every event. The event summary groups parsed severity, facility, and event
code so an agent can inspect frequent signals before requesting raw messages.

It also exposes unauthenticated process health endpoints at `/health/live` and
`/health/ready`. The MCP endpoint is `/mcp` and requires `SYSLOG_MCP_TOKEN` when set.

### Vendor Cache / Lookup
- `REDIS_URL` (optional; when reachable Redis is used, otherwise in-memory fallback is used)
- `VENDOR_LOOKUP_URL` (optional; API endpoint returning vendor mapping entries)
- `VENDOR_REFRESH_SECS` (default: `900`)
- `VENDOR_CACHE_PREFIX` (default: `vendor_cache`)

Expected lookup API payload formats:
- `[{ "ip": "10.0.0.1", "hostname": "edge-01", "vendor": "cisco" }, ...]`
- or `{ "items": [{ "ip": "...", "hostname": "...", "vendor": "..." }, ...] }`

## Notes

- ClickHouse schema is auto-created. Startup removes the obsolete `normalized_message`, `template`,
  and `template_fingerprint` columns from existing tables.
- `syslog_events` is partitioned by event datetime day (`toDate(toDateTime(ts_unix))`).
- ClickHouse TTL deletes rows older than `CLICKHOUSE_RETENTION_DAYS`.
- Event writes to ClickHouse are batched in-memory and flushed by size/time thresholds.
- Kafka intake has bounded in-flight concurrency. A record becomes commit-eligible only after its
  ClickHouse batch is acknowledged, and offsets advance contiguously per partition.
- ClickHouse inserts use bounded timeouts and retries. Exhaustion fails the process so a supervisor
  can restart it and Kafka can replay uncommitted records instead of allowing an unbounded backlog.
- Prometheus process and ingestion metrics are exposed at `http://METRICS_BIND/metrics`. Useful
  rate queries include `rate(netai_log_ingestor_events_persisted_total[5m])` and
  `rate(netai_log_ingestor_failures_total[5m])`.
- The former unused Qdrant and embedding compatibility code has been removed;
  ClickHouse is the syslog service's only event store.
- Vendor cache refresh is best-effort. Failed vendor API calls or Redis errors are logged and ingestion continues.

## Run

From repo root:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml
```

Run the independent query/MCP process:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml --bin syslog_mcp
```

The binary will try `.env` in the current working directory first, then `log_ingestor/.env` when launched from the repo root.

## TODO

- [ ] Add negative caching strategy for unknown hostnames.
- [ ] Add parser test corpus per vendor (Cisco, Fortinet, Juniper, Palo Alto, Arista, Aruba).
- [ ] Add metrics for parse confidence and unknown vendor rate.
