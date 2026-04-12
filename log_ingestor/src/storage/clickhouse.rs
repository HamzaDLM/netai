use anyhow::Result;
use clickhouse::{Client, Row};
use serde::Serialize;

pub const EVENTS_TABLE: &str = "syslog_events";

#[derive(Debug, Serialize, Row)]
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

pub fn build_client(base_url: &str, database: &str, user: &str, password: &str) -> Client {
    Client::default()
        .with_url(base_url)
        .with_user(user)
        .with_password(password)
        .with_database(database)
}

pub async fn ensure_events_table_exists(client: &Client) -> Result<()> {
    client
        .query(
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
            ORDER BY (ts_unix, hostname, event_id)
            ",
        )
        .execute()
        .await?;

    // Backward compatibility for existing deployments created before vendor columns existed.
    client
        .query("ALTER TABLE syslog_events ADD COLUMN IF NOT EXISTS vendor String")
        .execute()
        .await?;
    client
        .query("ALTER TABLE syslog_events ADD COLUMN IF NOT EXISTS facility String")
        .execute()
        .await?;
    client
        .query("ALTER TABLE syslog_events ADD COLUMN IF NOT EXISTS severity Int16 DEFAULT -1")
        .execute()
        .await?;
    client
        .query("ALTER TABLE syslog_events ADD COLUMN IF NOT EXISTS event_code String")
        .execute()
        .await?;

    Ok(())
}

pub async fn insert_event(client: &Client, row: &SyslogEventRow) -> Result<()> {
    let mut insert = client.insert(EVENTS_TABLE)?;
    insert.write(row).await?;
    insert.end().await?;
    Ok(())
}
