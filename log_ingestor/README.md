# log_ingestor

Standalone Rust log intelligence service. Its ingestion process consumes and
normalizes Kafka syslogs into ClickHouse; its independently runnable MCP process
owns all read access so NetAI never needs ClickHouse SQL or credentials.

## Runtime layout

```text
Kafka -> log_ingestor -> ClickHouse <- log_mcp <- NetAI
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
4. Run vendor-aware parsing and normalization:
   - detect vendor from explicit `vendor` when present, otherwise heuristics
   - extract metadata where possible (`facility`, `severity`, `event_code`)
   - apply common normalization (`IP`, `MAC`, UUID, numbers, etc.)
   - apply vendor-specific normalization rules
5. Write remaining events to ClickHouse table `syslog_events` (raw + normalized + metadata).

The ClickHouse `template` and `template_fingerprint` columns are still populated from the normalized message for compatibility, but the ingestion pipeline no longer embeds templates or upserts them into Qdrant.

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
- `CLICKHOUSE_URL` (default: `http://localhost:8123`)
- `CLICKHOUSE_DB` (default: `netops`)
- `CLICKHOUSE_USER` (default: `admin`)
- `CLICKHOUSE_PASSWORD` (default: `admin`)
- `CLICKHOUSE_RETENTION_DAYS` (default: `30`)
- `CLICKHOUSE_BATCH_SIZE` (default: `1000`)
- `CLICKHOUSE_FLUSH_INTERVAL_MS` (default: `1000`)
- `CLICKHOUSE_INSERT_QUEUE_CAPACITY` (default: `20000`)
- `IGNORED_SYSLOG_TEXTS` (optional comma/newline-separated substrings; defaults include `vfork couldn't find enough ressources` and `vfork couldn't find enough resources`)

### Log MCP/query service

- `LOG_MCP_BIND` (default: `0.0.0.0:8010`)
- `LOG_MCP_ALLOWED_HOSTS` (comma-separated MCP Host-header allowlist)
- `LOG_MCP_TOKEN` (optional bearer token; configure it outside local development)
- `LOG_QUERY_DEFAULT_WINDOW_SECS` (default: `3600`)
- `LOG_QUERY_MAX_WINDOW_SECS` (default: `604800`, seven days)
- `LOG_QUERY_MAX_RESULTS` (default: `200`)
- `LOG_QUERY_TIMEOUT_SECS` (default: `8`)

The MCP service exposes only typed, bounded, read-only operations:

- `logs_get_device_events`
- `logs_get_severity_summary`
- `logs_get_device_patterns`

It also exposes unauthenticated process health endpoints at `/health/live` and
`/health/ready`. The MCP endpoint is `/mcp` and requires `LOG_MCP_TOKEN` when set.

### Vendor Cache / Lookup
- `REDIS_URL` (optional; when reachable Redis is used, otherwise in-memory fallback is used)
- `VENDOR_LOOKUP_URL` (optional; API endpoint returning vendor mapping entries)
- `VENDOR_REFRESH_SECS` (default: `900`)
- `VENDOR_CACHE_PREFIX` (default: `vendor_cache`)

Expected lookup API payload formats:
- `[{ "ip": "10.0.0.1", "hostname": "edge-01", "vendor": "cisco" }, ...]`
- or `{ "items": [{ "ip": "...", "hostname": "...", "vendor": "..." }, ...] }`

## Notes

- ClickHouse schema is auto-created and auto-migrated for added metadata columns.
- `syslog_events` is partitioned by event datetime day (`toDate(toDateTime(ts_unix))`).
- ClickHouse TTL deletes rows older than `CLICKHOUSE_RETENTION_DAYS`.
- Event writes to ClickHouse are batched in-memory and flushed by size/time thresholds.
- The former unused Qdrant and embedding compatibility code has been removed;
  ClickHouse is the log service's only event store.
- Vendor cache refresh is best-effort. Failed vendor API calls or Redis errors are logged and ingestion continues.

## Run

From repo root:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml
```

Run the independent query/MCP process:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml --bin log_mcp
```

The binary will try `.env` in the current working directory first, then `log_ingestor/.env` when launched from the repo root.

## TODO

- [ ] Add negative caching strategy for unknown hostnames.
- [ ] Add parser/normalizer test corpus per vendor (Cisco, Fortinet, Juniper, Palo Alto, Arista, Aruba).
- [ ] Add metrics for parse confidence, unknown vendor rate, and raw-like template ratio.
