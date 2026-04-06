use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct IncomingSyslog {
    pub syslog_timestamp: i64,
    pub syslog_hostname: String,
    pub syslog_message: String,
    #[serde(default)]
    pub vendor: Option<String>,
}

#[derive(Debug, Clone)]
pub struct LogTemplate {
    pub id: Uuid,
    pub template: String,
}

#[derive(Debug, Serialize)]
pub struct QdrantPoint {
    pub id: Uuid,
    pub vector: Vec<f32>,
    pub payload: serde_json::Value,
}
