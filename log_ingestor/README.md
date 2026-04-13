# log_ingestor

Rust Kafka consumer that ingests syslogs, normalizes them, stores all events in ClickHouse, and stores unique normalized templates in Qdrant using real embedding vectors.

## Current Flow

1. Consume JSON messages from Kafka topic (`KAFKA_TOPIC`, default `syslogs`).
2. Parse each message into:
   - `syslog_timestamp`
   - `syslog_hostname`
   - `syslog_message`
   - optional `vendor`
3. Run vendor-aware parsing and normalization:
   - detect vendor from explicit `vendor` when present, otherwise heuristics
   - extract metadata where possible (`facility`, `severity`, `event_code`)
   - apply common normalization (`IP`, `MAC`, UUID, numbers, etc.)
   - apply vendor-specific normalization rules
4. Build a normalized template string.
5. Write **every event** to ClickHouse table `syslog_events` (raw + normalized + metadata).
6. Deduplicate templates in-memory using key: `vendor::template`.
7. For new templates only:
   - call embedding endpoint (`EMBEDDING_URL`) using OpenAI-compatible request format
   - validate vector size against `EMBEDDING_DIMENSION`
   - upsert into Qdrant collection (`QDRANT_COLLECTION`) with payload:
     - `template`
     - `vendor`
     - `dedup_key`

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

### Qdrant
- `QDRANT_URL` (default: `http://localhost:6333`)
- `QDRANT_COLLECTION` (default: `syslogs`)

### Embeddings
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
- If embedding endpoint is unavailable or returns wrong dimension, new template upserts fail for that event.
- Embedding requests use bounded concurrency, request pacing, and retries for `429`/`5xx` responses.
- Ingestion still writes raw/normalized event rows to ClickHouse before template vectorization.
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
