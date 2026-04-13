pub struct Config {
    pub kafka_brokers: String,
    pub kafka_topic: String,
    pub kafka_group_id: String,
    pub qdrant_url: String,
    pub qdrant_collection: String,
    pub clickhouse_url: String,
    pub clickhouse_db: String,
    pub clickhouse_user: String,
    pub clickhouse_password: String,
    pub clickhouse_retention_days: u64,
    pub clickhouse_batch_size: usize,
    pub clickhouse_flush_interval_ms: u64,
    pub clickhouse_insert_queue_capacity: usize,
    pub embedding_url: String,
    pub embedding_model: String,
    pub embedding_api_key: Option<String>,
    pub embedding_timeout_secs: u64,
    pub embedding_dimension: u64,
    pub embedding_max_in_flight: usize,
    pub embedding_max_requests_per_second: u64,
    pub embedding_max_retries: u32,
    pub embedding_retry_backoff_ms: u64,
    pub redis_url: Option<String>,
    pub vendor_lookup_url: Option<String>,
    pub vendor_refresh_secs: u64,
    pub vendor_cache_prefix: String,
}

impl Config {
    pub fn from_env() -> Self {
        Self::from_env_with(|key| std::env::var(key).ok())
    }

    fn from_env_with(get: impl Fn(&str) -> Option<String>) -> Self {
        let embedding_api_key =
            get("EMBEDDING_API_KEY").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let redis_url =
            get("REDIS_URL").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let vendor_lookup_url =
            get("VENDOR_LOOKUP_URL").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });

        Self {
            kafka_brokers: get("KAFKA_BROKERS").unwrap_or("localhost:9092".into()),
            kafka_topic: get("KAFKA_TOPIC").unwrap_or("syslogs".into()),
            kafka_group_id: get("KAFKA_GROUP_ID").unwrap_or("log-ingestor".into()),
            qdrant_url: get("QDRANT_URL").unwrap_or("http://localhost:6333".into()),
            qdrant_collection: get("QDRANT_COLLECTION").unwrap_or("syslogs".into()),
            clickhouse_url: get("CLICKHOUSE_URL").unwrap_or("http://localhost:8123".into()),
            clickhouse_db: get("CLICKHOUSE_DB").unwrap_or("netops".into()),
            clickhouse_user: get("CLICKHOUSE_USER").unwrap_or("admin".into()),
            clickhouse_password: get("CLICKHOUSE_PASSWORD").unwrap_or("admin".into()),
            clickhouse_retention_days: get("CLICKHOUSE_RETENTION_DAYS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(30),
            clickhouse_batch_size: get("CLICKHOUSE_BATCH_SIZE")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(1000),
            clickhouse_flush_interval_ms: get("CLICKHOUSE_FLUSH_INTERVAL_MS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(1000),
            clickhouse_insert_queue_capacity: get("CLICKHOUSE_INSERT_QUEUE_CAPACITY")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(20000),
            embedding_url: get("EMBEDDING_URL")
                .unwrap_or("http://localhost:8080/openai/embed".into()),
            embedding_model: get("EMBEDDING_MODEL").unwrap_or("text-embedding-3-small".into()),
            embedding_api_key,
            embedding_timeout_secs: get("EMBEDDING_TIMEOUT_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(30),
            embedding_dimension: get("EMBEDDING_DIMENSION")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(1536),
            embedding_max_in_flight: get("EMBEDDING_MAX_IN_FLIGHT")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(4),
            embedding_max_requests_per_second: get("EMBEDDING_MAX_REQUESTS_PER_SECOND")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(4),
            embedding_max_retries: get("EMBEDDING_MAX_RETRIES")
                .and_then(|v| v.parse::<u32>().ok())
                .unwrap_or(5),
            embedding_retry_backoff_ms: get("EMBEDDING_RETRY_BACKOFF_MS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(250),
            redis_url,
            vendor_lookup_url,
            vendor_refresh_secs: get("VENDOR_REFRESH_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(900),
            vendor_cache_prefix: get("VENDOR_CACHE_PREFIX").unwrap_or("vendor_cache".into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::Config;
    use std::collections::HashMap;

    #[test]
    fn from_env_with_uses_defaults_for_new_controls() {
        let cfg = Config::from_env_with(|_| None);
        assert_eq!(cfg.clickhouse_batch_size, 1000);
        assert_eq!(cfg.clickhouse_retention_days, 30);
        assert_eq!(cfg.clickhouse_flush_interval_ms, 1000);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 20000);
        assert_eq!(cfg.embedding_max_in_flight, 4);
        assert_eq!(cfg.embedding_max_requests_per_second, 4);
        assert_eq!(cfg.embedding_max_retries, 5);
        assert_eq!(cfg.embedding_retry_backoff_ms, 250);
    }

    #[test]
    fn from_env_with_parses_explicit_values_for_new_controls() {
        let vars = HashMap::from([
            ("CLICKHOUSE_BATCH_SIZE", "2500"),
            ("CLICKHOUSE_RETENTION_DAYS", "45"),
            ("CLICKHOUSE_FLUSH_INTERVAL_MS", "1500"),
            ("CLICKHOUSE_INSERT_QUEUE_CAPACITY", "64000"),
            ("EMBEDDING_MAX_IN_FLIGHT", "8"),
            ("EMBEDDING_MAX_REQUESTS_PER_SECOND", "12"),
            ("EMBEDDING_MAX_RETRIES", "9"),
            ("EMBEDDING_RETRY_BACKOFF_MS", "333"),
        ]);

        let cfg = Config::from_env_with(|k| vars.get(k).map(|v| v.to_string()));
        assert_eq!(cfg.clickhouse_batch_size, 2500);
        assert_eq!(cfg.clickhouse_retention_days, 45);
        assert_eq!(cfg.clickhouse_flush_interval_ms, 1500);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 64000);
        assert_eq!(cfg.embedding_max_in_flight, 8);
        assert_eq!(cfg.embedding_max_requests_per_second, 12);
        assert_eq!(cfg.embedding_max_retries, 9);
        assert_eq!(cfg.embedding_retry_backoff_ms, 333);
    }

    #[test]
    fn from_env_with_ignores_invalid_numeric_values() {
        let vars = HashMap::from([
            ("CLICKHOUSE_BATCH_SIZE", "abc"),
            ("CLICKHOUSE_RETENTION_DAYS", "bad"),
            ("CLICKHOUSE_FLUSH_INTERVAL_MS", "x"),
            ("CLICKHOUSE_INSERT_QUEUE_CAPACITY", "oops"),
            ("EMBEDDING_MAX_IN_FLIGHT", "nope"),
            ("EMBEDDING_MAX_REQUESTS_PER_SECOND", "nan"),
            ("EMBEDDING_MAX_RETRIES", "bad"),
            ("EMBEDDING_RETRY_BACKOFF_MS", "invalid"),
        ]);

        let cfg = Config::from_env_with(|k| vars.get(k).map(|v| v.to_string()));
        assert_eq!(cfg.clickhouse_batch_size, 1000);
        assert_eq!(cfg.clickhouse_retention_days, 30);
        assert_eq!(cfg.clickhouse_flush_interval_ms, 1000);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 20000);
        assert_eq!(cfg.embedding_max_in_flight, 4);
        assert_eq!(cfg.embedding_max_requests_per_second, 4);
        assert_eq!(cfg.embedding_max_retries, 5);
        assert_eq!(cfg.embedding_retry_backoff_ms, 250);
    }
}
