use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct IncomingSyslog {
    #[serde(deserialize_with = "crate::serde_helpers::timestamp::deserialize_unix_ts")]
    pub syslog_timestamp: i64,
    pub syslog_hostname: String,
    pub syslog_message: String,
    #[serde(default)]
    pub vendor: Option<String>,
}
