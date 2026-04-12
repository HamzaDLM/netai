use anyhow::Result;
use clickhouse::Client as ClickHouseClient;
use log::debug;
use once_cell::sync::Lazy;
use regex::Regex;
use reqwest::Client;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::sync::Arc;
use uuid::Uuid;

use crate::{
    config::Config,
    embedding::client::EmbeddingClient,
    processing::{
        dedup::TemplateDeduplicator, normalizer::normalize_message, parser::parse_syslog,
        template::build_template,
    },
    storage::{
        clickhouse::{
            SyslogEventRow, build_client as build_clickhouse_client, ensure_events_table_exists,
            insert_event,
        },
        qdrant::{ensure_collection_exists, fetch_existing_templates, upsert_point},
    },
    types::IncomingSyslog,
    vendor_cache::VendorCache,
};

static IPV4_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
        .expect("valid ipv4 regex")
});

pub struct Pipeline {
    dedup: TemplateDeduplicator,
    embedder: EmbeddingClient,
    http: Client,
    clickhouse: ClickHouseClient,
    vendor_cache: VendorCache,
    config: Arc<Config>,
}

impl Pipeline {
    pub fn new(config: Arc<Config>) -> Self {
        return Self {
            dedup: TemplateDeduplicator::new(),
            embedder: EmbeddingClient::new(&config),
            http: Client::new(),
            clickhouse: build_clickhouse_client(
                &config.clickhouse_url,
                &config.clickhouse_db,
                &config.clickhouse_user,
                &config.clickhouse_password,
            ),
            vendor_cache: VendorCache::new(config.clone()),
            config,
        };
    }

    pub async fn ensure_collection(&self) -> Result<()> {
        ensure_collection_exists(
            &self.http,
            &self.config.qdrant_url,
            &self.config.qdrant_collection,
            self.embedder.dimension(),
        )
        .await?;

        let templates = fetch_existing_templates(
            &self.http,
            &self.config.qdrant_url,
            &self.config.qdrant_collection,
        )
        .await?;

        for template in templates {
            self.dedup.mark_seen(template);
        }

        debug!(
            "dedup warmup loaded {} templates from Qdrant",
            self.dedup.len()
        );

        ensure_events_table_exists(&self.clickhouse).await?;
        Ok(())
    }

    pub async fn refresh_vendor_cache(&self) {
        self.vendor_cache.warmup(&self.http).await;
    }

    pub async fn process(&self, log: IncomingSyslog) -> Result<()> {
        debug!("processing log: {}", log.syslog_message);
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

        let template = build_template(normalized.clone());
        debug!("template result: {}", template.template);
        let dedup_key = format!("{}::{}", vendor, template.template);
        let template_fingerprint = fingerprint_template(&template.template);

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
            template: template.template.clone(),
            template_fingerprint,
        };

        insert_event(&self.clickhouse, &event_row).await?;

        if !self.dedup.is_new(&dedup_key) {
            debug!("dedup decision: not new");
            return Ok(());
        }
        debug!("dedup decision: new");

        let vector = self.embedder.embed(&template.template).await?;
        debug!("embedding result vector: {:?}", vector);

        upsert_point(
            &self.http,
            &self.config.qdrant_url,
            &self.config.qdrant_collection,
            template.id,
            vector,
            &template.template,
            &vendor,
            &dedup_key,
        )
        .await?;

        Ok(())
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
