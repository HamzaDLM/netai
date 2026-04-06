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

### Qdrant
- `QDRANT_URL` (default: `http://localhost:6333`)
- `QDRANT_COLLECTION` (default: `syslogs`)

### Embeddings
- `EMBEDDING_URL` (default: `http://localhost:8080/openai/embed`)
- `EMBEDDING_MODEL` (default: `text-embedding-3-small`)
- `EMBEDDING_API_KEY` (optional)
- `EMBEDDING_TIMEOUT_SECS` (default: `30`)
- `EMBEDDING_DIMENSION` (default: `1536`)

## Notes

- ClickHouse schema is auto-created and auto-migrated for added metadata columns.
- If embedding endpoint is unavailable or returns wrong dimension, new template upserts fail for that event.
- Ingestion still writes raw/normalized event rows to ClickHouse before template vectorization.

## Run

From repo root:

```bash
cargo run --manifest-path log_ingestor/Cargo.toml
```

## TODO

- [ ] Implement hostname -> vendor enrichment with a two-layer cache:
  - L1 in-process memory cache for very fast lookups
  - L2 Redis cache as shared/source-of-truth fallback
- [ ] Add background refresh + negative caching strategy for unknown hostnames.
- [ ] Add parser/normalizer test corpus per vendor (Cisco, Fortinet, Juniper, Palo Alto, Arista, Aruba).
- [ ] Add metrics for parse confidence, unknown vendor rate, and raw-like template ratio.
