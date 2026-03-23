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
}

impl Config {
    pub fn from_env() -> Self {
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
        }
    }
}
