use anyhow::{Result, bail};
use clickhouse::{Client, Row};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const EVENTS_TABLE: &str = "syslog_events";

#[derive(Clone, Debug, Deserialize, JsonSchema, Serialize, Row)]
pub struct SyslogEventRow {
    pub event_id: String,
    pub ts_unix: i64,
    pub hostname: String,
    pub vendor: String,
    pub facility: String,
    pub severity: i16,
    pub event_code: String,
    pub raw_message: String,
    pub normalized_message: String,
    pub template: String,
    pub template_fingerprint: u64,
}

#[derive(Deserialize, Row)]
struct ClickHouseVersionRow {
    version: String,
}

pub fn build_client(base_url: &str, database: &str, user: &str, password: &str) -> Client {
    Client::default()
        .with_url(base_url)
        .with_user(user)
        .with_password(password)
        .with_database(database)
}

pub async fn ensure_events_table_exists(client: &Client, retention_days: u64) -> Result<()> {
    let server = client
        .query("SELECT version() AS version")
        .fetch_one::<ClickHouseVersionRow>()
        .await?;
    if !supports_table_ttl(&server.version) {
        bail!(
            "ClickHouse {} is unsupported: table TTL requires version 19.6 or newer",
            server.version
        );
    }
    client
        .query(&events_table_ddl(retention_days))
        .execute()
        .await?;

    Ok(())
}

fn supports_table_ttl(version: &str) -> bool {
    let mut parts = version.split('.');
    let major = parts.next().and_then(|part| part.parse::<u64>().ok());
    let minor = parts.next().and_then(|part| part.parse::<u64>().ok());
    matches!((major, minor), (Some(major), Some(minor)) if (major, minor) >= (19, 6))
}

fn events_table_ddl(retention_days: u64) -> String {
    let ttl_days = retention_days.max(1);
    format!(
        "
            CREATE TABLE IF NOT EXISTS syslog_events (
                event_id String,
                ts_unix Int64,
                hostname String,
                vendor String,
                facility String,
                severity Int16,
                event_code String,
                raw_message String,
                normalized_message String,
                template String,
                template_fingerprint UInt64
            )
            ENGINE = MergeTree
            PARTITION BY toDate(toDateTime(ts_unix))
            ORDER BY (ts_unix, hostname, event_id)
            TTL toDateTime(ts_unix) + toIntervalDay({ttl_days})
            "
    )
}

pub async fn insert_events(client: &Client, rows: &[SyslogEventRow]) -> Result<()> {
    if rows.is_empty() {
        return Ok(());
    }

    let mut insert: clickhouse::insert::Insert<SyslogEventRow> = client.insert(EVENTS_TABLE)?;
    for row in rows {
        insert.write(row).await?;
    }
    insert.end().await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{events_table_ddl, supports_table_ttl};

    #[test]
    fn identifies_versions_with_table_ttl_support() {
        assert!(!supports_table_ttl("18.16.1"));
        assert!(!supports_table_ttl("19.5.9"));
        assert!(supports_table_ttl("19.6.3.18"));
        assert!(supports_table_ttl("24.8.12.28"));
        assert!(!supports_table_ttl("unknown"));
    }

    #[test]
    fn table_ddl_uses_compatible_delete_ttl_syntax() {
        let ddl = events_table_ddl(30);

        assert!(ddl.contains("TTL toDateTime(ts_unix) + toIntervalDay(30)"));
        assert!(!ddl.contains("DELETE"));
    }

    #[test]
    fn table_ddl_never_disables_retention() {
        assert!(events_table_ddl(0).contains("TTL toDateTime(ts_unix) + toIntervalDay(1)"));
    }
}
