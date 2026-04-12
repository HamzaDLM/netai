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
    pub embedding_url: String,
    pub embedding_model: String,
    pub embedding_api_key: Option<String>,
    pub embedding_timeout_secs: u64,
    pub embedding_dimension: u64,
    pub redis_url: Option<String>,
    pub vendor_lookup_url: Option<String>,
    pub vendor_refresh_secs: u64,
    pub vendor_cache_prefix: String,
}

impl Config {
    pub fn from_env() -> Self {
        let embedding_api_key = std::env::var("EMBEDDING_API_KEY")
            .ok()
            .and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let redis_url = std::env::var("REDIS_URL")
            .ok()
            .and_then(|v| if v.trim().is_empty() { None } else { Some(v) });
        let vendor_lookup_url = std::env::var("VENDOR_LOOKUP_URL")
            .ok()
            .and_then(|v| if v.trim().is_empty() { None } else { Some(v) });

        Self {
            kafka_brokers: std::env::var("KAFKA_BROKERS").unwrap_or("localhost:9092".into()),
            kafka_topic: std::env::var("KAFKA_TOPIC").unwrap_or("syslogs".into()),
            kafka_group_id: std::env::var("KAFKA_GROUP_ID").unwrap_or("log-ingestor".into()),
            qdrant_url: std::env::var("QDRANT_URL").unwrap_or("http://localhost:6333".into()),
            qdrant_collection: std::env::var("QDRANT_COLLECTION").unwrap_or("syslogs".into()),
            clickhouse_url: std::env::var("CLICKHOUSE_URL")
                .unwrap_or("http://localhost:8123".into()),
            clickhouse_db: std::env::var("CLICKHOUSE_DB").unwrap_or("netops".into()),
            clickhouse_user: std::env::var("CLICKHOUSE_USER").unwrap_or("admin".into()),
            clickhouse_password: std::env::var("CLICKHOUSE_PASSWORD").unwrap_or("admin".into()),
            embedding_url: std::env::var("EMBEDDING_URL")
                .unwrap_or("http://localhost:8080/openai/embed".into()),
            embedding_model: std::env::var("EMBEDDING_MODEL")
                .unwrap_or("text-embedding-3-small".into()),
            embedding_api_key,
            embedding_timeout_secs: std::env::var("EMBEDDING_TIMEOUT_SECS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(30),
            embedding_dimension: std::env::var("EMBEDDING_DIMENSION")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(1536),
            redis_url,
            vendor_lookup_url,
            vendor_refresh_secs: std::env::var("VENDOR_REFRESH_SECS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(900),
            vendor_cache_prefix: std::env::var("VENDOR_CACHE_PREFIX")
                .unwrap_or("vendor_cache".into()),
        }
    }
}
