pub struct Config {
    pub kafka_brokers: String,
    pub kafka_topic: String,
    pub kafka_group_id: String,
    pub clickhouse_url: String,
    pub clickhouse_db: String,
    pub clickhouse_user: String,
    pub clickhouse_password: String,
    pub clickhouse_retention_days: u64,
    pub clickhouse_batch_size: usize,
    pub clickhouse_flush_interval_ms: u64,
    pub clickhouse_insert_queue_capacity: usize,
    pub clickhouse_insert_max_retries: usize,
    pub clickhouse_insert_retry_backoff_ms: u64,
    pub clickhouse_insert_timeout_secs: u64,
    pub ingest_max_in_flight: usize,
    pub kafka_lag_poll_interval_secs: u64,
    pub metrics_bind: String,
    pub log_mcp_bind: String,
    pub log_mcp_allowed_hosts: Vec<String>,
    pub log_mcp_token: Option<String>,
    pub log_query_default_window_secs: u64,
    pub log_query_max_window_secs: u64,
    pub log_query_max_results: u32,
    pub log_query_timeout_secs: u64,
    pub ignored_syslog_texts: Vec<String>,
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
        let redis_url =
            get("REDIS_URL").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let vendor_lookup_url =
            get("VENDOR_LOOKUP_URL").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let ignored_syslog_texts =
            parse_ignored_syslog_texts(get("IGNORED_SYSLOG_TEXTS").as_deref());
        let log_mcp_token =
            get("LOG_MCP_TOKEN").and_then(|v| if v.trim().is_empty() { None } else { Some(v) });

        Self {
            kafka_brokers: get("KAFKA_BROKERS").unwrap_or("localhost:9092".into()),
            kafka_topic: get("KAFKA_TOPIC").unwrap_or("syslogs".into()),
            kafka_group_id: get("KAFKA_GROUP_ID").unwrap_or("log-ingestor".into()),
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
                .unwrap_or(100),
            clickhouse_insert_queue_capacity: get("CLICKHOUSE_INSERT_QUEUE_CAPACITY")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(20000),
            clickhouse_insert_max_retries: get("CLICKHOUSE_INSERT_MAX_RETRIES")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(5),
            clickhouse_insert_retry_backoff_ms: get("CLICKHOUSE_INSERT_RETRY_BACKOFF_MS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(250),
            clickhouse_insert_timeout_secs: get("CLICKHOUSE_INSERT_TIMEOUT_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(10),
            ingest_max_in_flight: get("INGEST_MAX_IN_FLIGHT")
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(256),
            kafka_lag_poll_interval_secs: get("KAFKA_LAG_POLL_INTERVAL_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(15),
            metrics_bind: get("METRICS_BIND").unwrap_or("0.0.0.0:9898".into()),
            log_mcp_bind: get("LOG_MCP_BIND").unwrap_or("0.0.0.0:8010".into()),
            log_mcp_allowed_hosts: get("LOG_MCP_ALLOWED_HOSTS")
                .map(|value| parse_csv(&value))
                .filter(|items| !items.is_empty())
                .unwrap_or_else(|| {
                    vec![
                        "localhost".into(),
                        "127.0.0.1".into(),
                        "::1".into(),
                        "log_mcp".into(),
                    ]
                }),
            log_mcp_token,
            log_query_default_window_secs: get("LOG_QUERY_DEFAULT_WINDOW_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(3600),
            log_query_max_window_secs: get("LOG_QUERY_MAX_WINDOW_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(604800),
            log_query_max_results: get("LOG_QUERY_MAX_RESULTS")
                .and_then(|v| v.parse::<u32>().ok())
                .unwrap_or(200),
            log_query_timeout_secs: get("LOG_QUERY_TIMEOUT_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(8),
            ignored_syslog_texts,
            redis_url,
            vendor_lookup_url,
            vendor_refresh_secs: get("VENDOR_REFRESH_SECS")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(900),
            vendor_cache_prefix: get("VENDOR_CACHE_PREFIX").unwrap_or("vendor_cache".into()),
        }
    }
}

fn parse_csv(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn parse_ignored_syslog_texts(value: Option<&str>) -> Vec<String> {
    let configured = value
        .map(|raw| {
            raw.split('\n')
                .flat_map(|line| line.split(','))
                .map(str::trim)
                .filter(|text| !text.is_empty())
                .map(ToOwned::to_owned)
                .collect::<Vec<_>>()
        })
        .filter(|items| !items.is_empty());

    configured.unwrap_or_else(|| {
        vec![
            "vfork couldn't find enough ressources".to_string(),
            "vfork couldn't find enough resources".to_string(),
        ]
    })
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
        assert_eq!(cfg.clickhouse_flush_interval_ms, 100);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 20000);
        assert_eq!(cfg.clickhouse_insert_max_retries, 5);
        assert_eq!(cfg.clickhouse_insert_retry_backoff_ms, 250);
        assert_eq!(cfg.clickhouse_insert_timeout_secs, 10);
        assert_eq!(cfg.ingest_max_in_flight, 256);
        assert_eq!(cfg.kafka_lag_poll_interval_secs, 15);
        assert_eq!(cfg.metrics_bind, "0.0.0.0:9898");
        assert_eq!(cfg.log_mcp_bind, "0.0.0.0:8010");
        assert!(cfg.log_mcp_allowed_hosts.contains(&"log_mcp".to_string()));
        assert!(cfg.log_mcp_token.is_none());
        assert_eq!(cfg.log_query_default_window_secs, 3600);
        assert_eq!(cfg.log_query_max_window_secs, 604800);
        assert_eq!(cfg.log_query_max_results, 200);
        assert_eq!(cfg.log_query_timeout_secs, 8);
        assert_eq!(
            cfg.ignored_syslog_texts,
            vec![
                "vfork couldn't find enough ressources".to_string(),
                "vfork couldn't find enough resources".to_string(),
            ]
        );
    }

    #[test]
    fn from_env_with_parses_explicit_values_for_new_controls() {
        let vars = HashMap::from([
            ("CLICKHOUSE_BATCH_SIZE", "2500"),
            ("CLICKHOUSE_RETENTION_DAYS", "45"),
            ("CLICKHOUSE_FLUSH_INTERVAL_MS", "1500"),
            ("CLICKHOUSE_INSERT_QUEUE_CAPACITY", "64000"),
            ("CLICKHOUSE_INSERT_MAX_RETRIES", "7"),
            ("CLICKHOUSE_INSERT_RETRY_BACKOFF_MS", "500"),
            ("CLICKHOUSE_INSERT_TIMEOUT_SECS", "20"),
            ("INGEST_MAX_IN_FLIGHT", "512"),
            ("KAFKA_LAG_POLL_INTERVAL_SECS", "30"),
            ("METRICS_BIND", "127.0.0.1:9988"),
            ("LOG_MCP_BIND", "127.0.0.1:9010"),
            ("LOG_MCP_ALLOWED_HOSTS", "logs.example.com,logs.internal"),
            ("LOG_MCP_TOKEN", "secret"),
            ("LOG_QUERY_DEFAULT_WINDOW_SECS", "7200"),
            ("LOG_QUERY_MAX_WINDOW_SECS", "1209600"),
            ("LOG_QUERY_MAX_RESULTS", "500"),
            ("LOG_QUERY_TIMEOUT_SECS", "12"),
            ("IGNORED_SYSLOG_TEXTS", "noise one,noise two\nnoise three"),
        ]);

        let cfg = Config::from_env_with(|k| vars.get(k).map(|v| v.to_string()));
        assert_eq!(cfg.clickhouse_batch_size, 2500);
        assert_eq!(cfg.clickhouse_retention_days, 45);
        assert_eq!(cfg.clickhouse_flush_interval_ms, 1500);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 64000);
        assert_eq!(cfg.clickhouse_insert_max_retries, 7);
        assert_eq!(cfg.clickhouse_insert_retry_backoff_ms, 500);
        assert_eq!(cfg.clickhouse_insert_timeout_secs, 20);
        assert_eq!(cfg.ingest_max_in_flight, 512);
        assert_eq!(cfg.kafka_lag_poll_interval_secs, 30);
        assert_eq!(cfg.metrics_bind, "127.0.0.1:9988");
        assert_eq!(cfg.log_mcp_bind, "127.0.0.1:9010");
        assert_eq!(
            cfg.log_mcp_allowed_hosts,
            vec!["logs.example.com", "logs.internal"]
        );
        assert_eq!(cfg.log_mcp_token.as_deref(), Some("secret"));
        assert_eq!(cfg.log_query_default_window_secs, 7200);
        assert_eq!(cfg.log_query_max_window_secs, 1209600);
        assert_eq!(cfg.log_query_max_results, 500);
        assert_eq!(cfg.log_query_timeout_secs, 12);
        assert_eq!(
            cfg.ignored_syslog_texts,
            vec![
                "noise one".to_string(),
                "noise two".to_string(),
                "noise three".to_string(),
            ]
        );
    }

    #[test]
    fn from_env_with_ignores_invalid_numeric_values() {
        let vars = HashMap::from([
            ("CLICKHOUSE_BATCH_SIZE", "abc"),
            ("CLICKHOUSE_RETENTION_DAYS", "bad"),
            ("CLICKHOUSE_FLUSH_INTERVAL_MS", "x"),
            ("CLICKHOUSE_INSERT_QUEUE_CAPACITY", "oops"),
            ("CLICKHOUSE_INSERT_MAX_RETRIES", "none"),
            ("CLICKHOUSE_INSERT_RETRY_BACKOFF_MS", "later"),
            ("CLICKHOUSE_INSERT_TIMEOUT_SECS", "eventually"),
            ("INGEST_MAX_IN_FLIGHT", "many"),
            ("KAFKA_LAG_POLL_INTERVAL_SECS", "sometimes"),
        ]);

        let cfg = Config::from_env_with(|k| vars.get(k).map(|v| v.to_string()));
        assert_eq!(cfg.clickhouse_batch_size, 1000);
        assert_eq!(cfg.clickhouse_retention_days, 30);
        assert_eq!(cfg.clickhouse_flush_interval_ms, 100);
        assert_eq!(cfg.clickhouse_insert_queue_capacity, 20000);
        assert_eq!(cfg.clickhouse_insert_max_retries, 5);
        assert_eq!(cfg.clickhouse_insert_retry_backoff_ms, 250);
        assert_eq!(cfg.clickhouse_insert_timeout_secs, 10);
        assert_eq!(cfg.ingest_max_in_flight, 256);
        assert_eq!(cfg.kafka_lag_poll_interval_secs, 15);
    }
}
