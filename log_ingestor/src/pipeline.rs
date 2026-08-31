use anyhow::{Result, anyhow, bail};
use clickhouse::Client as ClickHouseClient;
use log::{debug, error, warn};
use once_cell::sync::Lazy;
use regex::Regex;
use reqwest::Client;
use std::sync::Arc;
use tokio::{
    sync::{mpsc, oneshot},
    time::{self, Duration, Instant, MissedTickBehavior},
};
use uuid::Uuid;

use crate::{
    config::Config,
    metrics::Metrics,
    processing::parser::parse_syslog,
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
    clickhouse_tx: mpsc::Sender<QueuedEvent>,
    vendor_cache: VendorCache,
    config: Arc<Config>,
    metrics: Metrics,
}

struct QueuedEvent {
    row: SyslogEventRow,
    persisted: oneshot::Sender<Result<(), String>>,
}

#[derive(Clone, Copy)]
struct WriterConfig {
    batch_size: usize,
    flush_interval: Duration,
    max_retries: usize,
    retry_backoff: Duration,
    insert_timeout: Duration,
}

impl Pipeline {
    pub fn new(config: Arc<Config>, metrics: Metrics) -> Self {
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
        let writer_config = WriterConfig {
            batch_size: config.clickhouse_batch_size.max(1),
            flush_interval: Duration::from_millis(config.clickhouse_flush_interval_ms.max(100)),
            max_retries: config.clickhouse_insert_max_retries,
            retry_backoff: Duration::from_millis(config.clickhouse_insert_retry_backoff_ms.max(1)),
            insert_timeout: Duration::from_secs(config.clickhouse_insert_timeout_secs.max(1)),
        };
        let writer_client = clickhouse.clone();
        let writer_metrics = metrics.clone();
        tokio::spawn(async move {
            if let Err(error) =
                run_clickhouse_writer(writer_client, clickhouse_rx, writer_config, writer_metrics)
                    .await
            {
                error!("clickhouse writer stopped: {error:#}");
            }
        });

        Self {
            http: Client::new(),
            clickhouse,
            clickhouse_tx,
            vendor_cache: VendorCache::new(config.clone()),
            config,
            metrics,
        }
    }

    pub async fn ensure_storage(&self) -> Result<()> {
        ensure_events_table_exists(&self.clickhouse, self.config.clickhouse_retention_days).await?;
        Ok(())
    }

    pub async fn refresh_vendor_cache(&self) {
        self.vendor_cache.warmup(&self.http).await;
    }

    pub async fn process(&self, log: IncomingSyslog) -> Result<()> {
        // debug!("processing log: {}", log.syslog_message);
        if should_ignore_message(&log.syslog_message, &self.config.ignored_syslog_texts) {
            debug!("ignoring syslog line matched configured ignored text");
            self.metrics.event_filtered();
            return Ok(());
        }

        let parsed = parse_syslog(&log);

        let source_ip = extract_ip(&log.syslog_message);
        let vendor = match self
            .vendor_cache
            .resolve_vendor(&log.syslog_hostname, source_ip.as_deref())
            .await
        {
            Some(vendor) if !vendor.trim().is_empty() => vendor,
            _ => parsed.vendor,
        };

        let event_row = SyslogEventRow {
            event_id: Uuid::new_v4().to_string(),
            ts_unix: log.syslog_timestamp,
            hostname: log.syslog_hostname,
            vendor,
            facility: parsed.facility.unwrap_or_default(),
            severity: parsed.severity.map(i16::from).unwrap_or(-1),
            event_code: parsed.event_code.unwrap_or_default(),
            raw_message: log.syslog_message,
        };

        let permit = self
            .clickhouse_tx
            .reserve()
            .await
            .map_err(|_| anyhow!("clickhouse writer task unavailable"))?;
        let (persisted, persistence) = oneshot::channel();
        self.metrics.clickhouse_queued();
        permit.send(QueuedEvent {
            row: event_row,
            persisted,
        });

        match persistence.await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => bail!(error),
            Err(_) => bail!("clickhouse writer stopped before acknowledging the event"),
        }
    }
}

async fn run_clickhouse_writer(
    client: ClickHouseClient,
    mut rx: mpsc::Receiver<QueuedEvent>,
    config: WriterConfig,
    metrics: Metrics,
) -> Result<()> {
    let mut batch: Vec<QueuedEvent> = Vec::with_capacity(config.batch_size);
    let mut ticker = time::interval_at(
        Instant::now() + config.flush_interval,
        config.flush_interval,
    );
    ticker.set_missed_tick_behavior(MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            maybe_row = rx.recv() => {
                match maybe_row {
                    Some(row) => {
                        metrics.clickhouse_dequeued();
                        batch.push(row);
                        if batch.len() >= config.batch_size {
                            flush_with_retry(&client, &mut batch, config, &metrics).await?;
                        }
                    }
                    None => {
                        flush_with_retry(&client, &mut batch, config, &metrics).await?;
                        break;
                    }
                }
            }
            _ = ticker.tick() => {
                if !batch.is_empty() {
                    flush_with_retry(&client, &mut batch, config, &metrics).await?;
                }
            }
        }
    }

    Ok(())
}

async fn flush_with_retry(
    client: &ClickHouseClient,
    batch: &mut Vec<QueuedEvent>,
    config: WriterConfig,
    metrics: &Metrics,
) -> Result<()> {
    if batch.is_empty() {
        return Ok(());
    }

    let mut retries = 0usize;
    loop {
        let started = std::time::Instant::now();
        let rows = batch.iter().map(|event| &event.row).collect::<Vec<_>>();
        let result = match time::timeout(config.insert_timeout, insert_events(client, &rows)).await
        {
            Ok(result) => result,
            Err(_) => Err(anyhow!(
                "clickhouse batch insert timed out after {} seconds",
                config.insert_timeout.as_secs()
            )),
        };
        metrics.observe_clickhouse_batch(batch.len(), started.elapsed().as_secs_f64());
        match result {
            Ok(_) => {
                if retries > 0 {
                    warn!(
                        "recovered clickhouse insert after {} retry attempts; flushed {} rows",
                        retries,
                        batch.len()
                    );
                }
                metrics.events_persisted(batch.len() as u64);
                for event in batch.drain(..) {
                    let _ = event.persisted.send(Ok(()));
                }
                return Ok(());
            }
            Err(err) => {
                metrics.failure("clickhouse_insert");
                if retries >= config.max_retries {
                    let message = format!(
                        "clickhouse batch insert failed after {} attempts: {err:#}",
                        retries + 1
                    );
                    for event in batch.drain(..) {
                        let _ = event.persisted.send(Err(message.clone()));
                    }
                    bail!(message);
                }
                retries += 1;
                metrics.clickhouse_insert_retried();
                let delay = retry_delay(config.retry_backoff, retries);
                error!(
                    "clickhouse batch insert failed (attempt {} of {}), retrying in {} ms: {err:#}",
                    retries,
                    config.max_retries + 1,
                    delay.as_millis()
                );
                time::sleep(delay).await;
            }
        }
    }
}

fn retry_delay(base: Duration, retry_number: usize) -> Duration {
    let exponent = retry_number.saturating_sub(1).min(7) as u32;
    base.saturating_mul(2u32.saturating_pow(exponent))
        .min(Duration::from_secs(30))
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
    use super::{Pipeline, QueuedEvent, retry_delay, should_ignore_message};
    use crate::{
        config::Config, metrics::Metrics, types::IncomingSyslog, vendor_cache::VendorCache,
    };
    use reqwest::Client;
    use std::sync::Arc;
    use tokio::{
        sync::mpsc,
        time::{Duration, timeout},
    };
    use uuid::Uuid;

    fn test_config() -> Arc<Config> {
        let mut config = Config::from_env();
        config.redis_url = None;
        config.vendor_lookup_url = None;
        Arc::new(config)
    }

    fn test_pipeline() -> (Pipeline, mpsc::Receiver<QueuedEvent>) {
        let config = test_config();
        let clickhouse = crate::storage::clickhouse::build_client(
            &config.clickhouse_url,
            &config.clickhouse_db,
            &config.clickhouse_user,
            &config.clickhouse_password,
        );
        let (clickhouse_tx, clickhouse_rx) = mpsc::channel(4);
        let pipeline = Pipeline {
            http: Client::new(),
            clickhouse,
            clickhouse_tx,
            vendor_cache: VendorCache::new(config.clone()),
            config,
            metrics: Metrics::new().expect("metrics registry"),
        };
        (pipeline, clickhouse_rx)
    }

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

    #[test]
    fn clickhouse_retry_backoff_is_exponential_and_capped() {
        assert_eq!(
            retry_delay(Duration::from_millis(250), 1),
            Duration::from_millis(250)
        );
        assert_eq!(
            retry_delay(Duration::from_millis(250), 3),
            Duration::from_secs(1)
        );
        assert_eq!(
            retry_delay(Duration::from_secs(10), 8),
            Duration::from_secs(30)
        );
    }

    #[tokio::test]
    async fn process_enqueues_clickhouse_row_with_current_pipeline_shape() {
        let (pipeline, mut rx) = test_pipeline();
        let log = IncomingSyslog {
            syslog_timestamp: 1_712_345_678,
            syslog_hostname: "router-edge-01".to_string(),
            syslog_message: "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down"
                .to_string(),
            vendor: None,
        };

        let process = tokio::spawn(async move { pipeline.process(log).await });

        let queued = timeout(Duration::from_secs(1), rx.recv())
            .await
            .expect("receive row before timeout")
            .expect("row should be queued");
        let row = &queued.row;

        assert!(Uuid::parse_str(&row.event_id).is_ok());
        assert_eq!(row.ts_unix, 1_712_345_678);
        assert_eq!(row.hostname, "router-edge-01");
        assert_eq!(row.vendor, "cisco");
        assert_eq!(row.facility, "LINK");
        assert_eq!(row.severity, 3);
        assert_eq!(row.event_code, "UPDOWN");
        assert_eq!(
            row.raw_message,
            "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down"
        );
        queued
            .persisted
            .send(Ok(()))
            .expect("processing task should await persistence");
        process
            .await
            .expect("processing task should join")
            .expect("process log");
    }

    #[tokio::test]
    async fn process_skips_ignored_messages_without_enqueuing_rows() {
        let (pipeline, mut rx) = test_pipeline();
        let log = IncomingSyslog {
            syslog_timestamp: 1_700_000_000,
            syslog_hostname: "router-edge-01".to_string(),
            syslog_message: "kernel: VFORK couldn't find enough ressources for process 123"
                .to_string(),
            vendor: None,
        };

        pipeline
            .process(log)
            .await
            .expect("ignored message should not fail");

        assert!(timeout(Duration::from_millis(50), rx.recv()).await.is_err());
    }
}
