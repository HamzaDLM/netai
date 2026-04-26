# log_ingestor

Rust Kafka consumer that ingests syslogs, filters known noisy lines, normalizes remaining events, and stores them in ClickHouse.

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

### Qdrant (legacy, not used by current ingestion flow)
- `QDRANT_URL` (default: `http://localhost:6333`)
- `QDRANT_COLLECTION` (default: `syslogs`)

### Embeddings (legacy, not used by current ingestion flow)
- `EMBEDDING_URL` (default: `http://localhost:8080/openai/embed`)
- `EMBEDDING_MODEL` (default: `text-embedding-3-small`)
- `EMBEDDING_API_KEY` (optional)
- `EMBEDDING_TIMEOUT_SECS` (default: `30`)
- `EMBEDDING_DIMENSION` (default: `1536`)
- `EMBEDDING_MAX_IN_FLIGHT` (default: `4`)
- `EMBEDDING_MAX_REQUESTS_PER_SECOND` (default: `4`, set `0` to disable request pacing)
- `EMBEDDING_MAX_RETRIES` (default: `5`)
- `EMBEDDING_RETRY_BACKOFF_MS` (default: `250`)

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
- Template vectorization is currently disabled to avoid high embedding cost on noisy production syslog data.
- Vendor cache refresh is best-effort. Failed vendor API calls or Redis errors are logged and ingestion continues.

## Run

From repo root:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml
```

## TODO

- [ ] Add negative caching strategy for unknown hostnames.
- [ ] Add parser/normalizer test corpus per vendor (Cisco, Fortinet, Juniper, Palo Alto, Arista, Aruba).
- [ ] Add metrics for parse confidence, unknown vendor rate, and raw-like template ratio.
