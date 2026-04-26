use anyhow::Result;
use clickhouse::Client as ClickHouseClient;
use log::{debug, error, warn};
use once_cell::sync::Lazy;
use regex::Regex;
use reqwest::Client;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::sync::Arc;
use tokio::{
    sync::mpsc,
    time::{self, Duration, MissedTickBehavior},
};
use uuid::Uuid;

use crate::{
    config::Config,
    processing::{normalizer::normalize_message, parser::parse_syslog},
    storage::clickhouse::{
        SyslogEventRow, build_client as build_clickhouse_client, ensure_events_table_exists,
        insert_events,
    },
    types::IncomingSyslog,
    vendor_cache::VendorCache,
};

static IPV4_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
        .expect("valid ipv4 regex")
});

pub struct Pipeline {
    http: Client,
    clickhouse: ClickHouseClient,
    clickhouse_tx: mpsc::Sender<SyslogEventRow>,
    vendor_cache: VendorCache,
    config: Arc<Config>,
}

impl Pipeline {
    pub fn new(config: Arc<Config>) -> Self {
        let clickhouse = build_clickhouse_client(
            &config.clickhouse_url,
            &config.clickhouse_db,
            &config.clickhouse_user,
            &config.clickhouse_password,
        );
        let (clickhouse_tx, clickhouse_rx) = mpsc::channel(
            config
                .clickhouse_insert_queue_capacity
                .max(config.clickhouse_batch_size.max(1)),
        );
        let flush_interval = Duration::from_millis(config.clickhouse_flush_interval_ms.max(100));
        let flush_batch_size = config.clickhouse_batch_size.max(1);
        let writer_client = clickhouse.clone();
        tokio::spawn(async move {
            run_clickhouse_writer(
                writer_client,
                clickhouse_rx,
                flush_batch_size,
                flush_interval,
            )
            .await;
        });

        return Self {
            http: Client::new(),
            clickhouse,
            clickhouse_tx,
            vendor_cache: VendorCache::new(config.clone()),
            config,
        };
    }

    pub async fn ensure_storage(&self) -> Result<()> {
        ensure_events_table_exists(&self.clickhouse, self.config.clickhouse_retention_days).await?;
        Ok(())
    }

    pub async fn refresh_vendor_cache(&self) {
        self.vendor_cache.warmup(&self.http).await;
    }

    pub async fn process(&self, log: IncomingSyslog) -> Result<()> {
        debug!("processing log: {}", log.syslog_message);
        if should_ignore_message(&log.syslog_message, &self.config.ignored_syslog_texts) {
            debug!("ignoring syslog line matched configured ignored text");
            return Ok(());
        }

        let parsed = parse_syslog(&log);
        let normalized = normalize_message(&parsed);
        debug!("normalized result: {}", normalized);

        let source_ip = extract_ip(&log.syslog_message);
        let vendor = match self
            .vendor_cache
            .resolve_vendor(&log.syslog_hostname, source_ip.as_deref())
            .await
        {
            Some(vendor) if !vendor.trim().is_empty() => vendor,
            _ => parsed.vendor.clone(),
        };

        let template = normalized.clone();
        let template_fingerprint = fingerprint_template(&template);

        let event_row = SyslogEventRow {
            event_id: Uuid::new_v4().to_string(),
            ts_unix: log.syslog_timestamp,
            hostname: log.syslog_hostname.clone(),
            vendor: vendor.clone(),
            facility: parsed.facility.clone().unwrap_or_default(),
            severity: parsed.severity.map(i16::from).unwrap_or(-1),
            event_code: parsed.event_code.clone().unwrap_or_default(),
            raw_message: log.syslog_message.clone(),
            normalized_message: normalized.clone(),
            template,
            template_fingerprint,
        };

        self.clickhouse_tx
            .send(event_row)
            .await
            .map_err(|err| anyhow::anyhow!("clickhouse writer task unavailable: {err}"))?;

        Ok(())
    }
}

async fn run_clickhouse_writer(
    client: ClickHouseClient,
    mut rx: mpsc::Receiver<SyslogEventRow>,
    batch_size: usize,
    flush_interval: Duration,
) {
    let mut batch: Vec<SyslogEventRow> = Vec::with_capacity(batch_size);
    let mut ticker = time::interval(flush_interval);
    ticker.set_missed_tick_behavior(MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            maybe_row = rx.recv() => {
                match maybe_row {
                    Some(row) => {
                        batch.push(row);
                        if batch.len() >= batch_size {
                            flush_with_retry(&client, &mut batch).await;
                        }
                    }
                    None => {
                        flush_with_retry(&client, &mut batch).await;
                        break;
                    }
                }
            }
            _ = ticker.tick() => {
                if !batch.is_empty() {
                    flush_with_retry(&client, &mut batch).await;
                }
            }
        }
    }
}

async fn flush_with_retry(client: &ClickHouseClient, batch: &mut Vec<SyslogEventRow>) {
    if batch.is_empty() {
        return;
    }

    let mut attempts = 0usize;
    loop {
        match insert_events(client, batch).await {
            Ok(_) => {
                if attempts > 0 {
                    warn!(
                        "recovered clickhouse insert after {} retry attempts; flushed {} rows",
                        attempts,
                        batch.len()
                    );
                }
                batch.clear();
                return;
            }
            Err(err) => {
                attempts += 1;
                error!(
                    "clickhouse batch insert failed (attempt {}), retrying in 1s: {err:#}",
                    attempts
                );
                time::sleep(Duration::from_secs(1)).await;
            }
        }
    }
}

fn fingerprint_template(template: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    template.hash(&mut hasher);
    hasher.finish()
}

fn extract_ip(message: &str) -> Option<String> {
    IPV4_RE.find(message).map(|m| m.as_str().to_string())
}

fn should_ignore_message(message: &str, ignored_texts: &[String]) -> bool {
    let message = message.to_lowercase();
    ignored_texts
        .iter()
        .map(|text| text.trim())
        .filter(|text| !text.is_empty())
        .any(|text| message.contains(&text.to_lowercase()))
}

#[cfg(test)]
mod tests {
    use super::should_ignore_message;

    #[test]
    fn should_ignore_message_matches_configured_substrings_case_insensitively() {
        let ignored_texts = vec!["vfork couldn't find enough ressources".to_string()];

        assert!(should_ignore_message(
            "kernel: VFORK couldn't find enough ressources for process 123",
            &ignored_texts
        ));
    }

    #[test]
    fn should_ignore_message_ignores_blank_patterns() {
        let ignored_texts = vec!["".to_string(), "   ".to_string()];

        assert!(!should_ignore_message(
            "ordinary interface state transition",
            &ignored_texts
        ));
    }
}
