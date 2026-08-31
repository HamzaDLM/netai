use std::{net::SocketAddr, sync::Arc};

use anyhow::Result;
use axum::{
    Router,
    extract::State,
    http::{StatusCode, header},
    response::{IntoResponse, Response},
    routing::get,
};
use log::info;
use prometheus::{
    Encoder, GaugeVec, Histogram, HistogramOpts, IntCounter, IntCounterVec, IntGauge, IntGaugeVec,
    Opts, Registry, TextEncoder, process_collector::ProcessCollector,
};

#[derive(Clone)]
pub struct Metrics {
    inner: Arc<MetricsInner>,
}

struct MetricsInner {
    registry: Registry,
    kafka_messages_received: IntCounter,
    kafka_messages_malformed: IntCounter,
    kafka_messages_without_payload: IntCounter,
    kafka_offsets_stored: IntCounter,
    kafka_lag: IntGaugeVec,
    kafka_processed_per_second: GaugeVec,
    processing_in_flight: IntGauge,
    events_filtered: IntCounter,
    events_persisted: IntCounter,
    failures: IntCounterVec,
    clickhouse_queue_depth: IntGauge,
    clickhouse_batch_rows: Histogram,
    clickhouse_batch_duration_seconds: Histogram,
    clickhouse_insert_retries: IntCounter,
}

impl Metrics {
    pub fn new() -> Result<Self, prometheus::Error> {
        let registry = Registry::new();
        let kafka_messages_received = register_counter(
            &registry,
            "netai_log_ingestor_kafka_messages_received_total",
            "Kafka records received by the log ingestor.",
        )?;
        let kafka_messages_malformed = register_counter(
            &registry,
            "netai_log_ingestor_kafka_messages_malformed_total",
            "Kafka records discarded because their payload was malformed.",
        )?;
        let kafka_messages_without_payload = register_counter(
            &registry,
            "netai_log_ingestor_kafka_messages_without_payload_total",
            "Kafka records discarded because they had no payload.",
        )?;
        let kafka_offsets_stored = register_counter(
            &registry,
            "netai_log_ingestor_kafka_offsets_stored_total",
            "Contiguous Kafka offsets made eligible for commit after processing.",
        )?;
        let kafka_lag = IntGaugeVec::new(
            Opts::new(
                "netai_log_ingestor_kafka_lag",
                "Difference between the Kafka high watermark and committed offset.",
            ),
            &["topic", "partition"],
        )?;
        registry.register(Box::new(kafka_lag.clone()))?;
        let kafka_processed_per_second = GaugeVec::new(
            Opts::new(
                "netai_log_ingestor_kafka_committed_messages_per_second",
                "Observed Kafka committed-offset rate by partition.",
            ),
            &["topic", "partition"],
        )?;
        registry.register(Box::new(kafka_processed_per_second.clone()))?;
        let processing_in_flight = register_gauge(
            &registry,
            "netai_log_ingestor_processing_in_flight",
            "Records currently being processed or awaiting ClickHouse persistence.",
        )?;
        let events_filtered = register_counter(
            &registry,
            "netai_log_ingestor_events_filtered_total",
            "Events intentionally filtered before ClickHouse persistence.",
        )?;
        let events_persisted = register_counter(
            &registry,
            "netai_log_ingestor_events_persisted_total",
            "Events successfully persisted to ClickHouse.",
        )?;
        let failures = IntCounterVec::new(
            Opts::new(
                "netai_log_ingestor_failures_total",
                "Log-ingestion failures partitioned by processing stage.",
            ),
            &["stage"],
        )?;
        registry.register(Box::new(failures.clone()))?;
        let clickhouse_queue_depth = register_gauge(
            &registry,
            "netai_log_ingestor_clickhouse_queue_depth",
            "Events waiting in the bounded ClickHouse insertion queue.",
        )?;
        let clickhouse_batch_rows = Histogram::with_opts(
            HistogramOpts::new(
                "netai_log_ingestor_clickhouse_batch_rows",
                "Number of rows in each attempted ClickHouse batch.",
            )
            .buckets(vec![1.0, 10.0, 50.0, 100.0, 250.0, 500.0, 1_000.0, 2_500.0]),
        )?;
        registry.register(Box::new(clickhouse_batch_rows.clone()))?;
        let clickhouse_batch_duration_seconds = Histogram::with_opts(
            HistogramOpts::new(
                "netai_log_ingestor_clickhouse_batch_duration_seconds",
                "ClickHouse batch insertion attempt duration in seconds.",
            )
            .buckets(vec![
                0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
            ]),
        )?;
        registry.register(Box::new(clickhouse_batch_duration_seconds.clone()))?;
        let clickhouse_insert_retries = register_counter(
            &registry,
            "netai_log_ingestor_clickhouse_insert_retries_total",
            "ClickHouse batch insertion retries.",
        )?;
        registry.register(Box::new(ProcessCollector::for_self()))?;

        Ok(Self {
            inner: Arc::new(MetricsInner {
                registry,
                kafka_messages_received,
                kafka_messages_malformed,
                kafka_messages_without_payload,
                kafka_offsets_stored,
                kafka_lag,
                kafka_processed_per_second,
                processing_in_flight,
                events_filtered,
                events_persisted,
                failures,
                clickhouse_queue_depth,
                clickhouse_batch_rows,
                clickhouse_batch_duration_seconds,
                clickhouse_insert_retries,
            }),
        })
    }

    pub fn kafka_message_received(&self) {
        self.inner.kafka_messages_received.inc();
    }

    pub fn kafka_message_malformed(&self) {
        self.inner.kafka_messages_malformed.inc();
    }

    pub fn kafka_message_without_payload(&self) {
        self.inner.kafka_messages_without_payload.inc();
    }

    pub fn kafka_offset_stored(&self, count: u64) {
        self.inner.kafka_offsets_stored.inc_by(count);
    }

    pub fn observe_kafka_partition(
        &self,
        topic: &str,
        partition: &str,
        lag: i64,
        processed_per_second: f64,
    ) {
        self.inner
            .kafka_lag
            .with_label_values(&[topic, partition])
            .set(lag);
        self.inner
            .kafka_processed_per_second
            .with_label_values(&[topic, partition])
            .set(processed_per_second);
    }

    pub fn processing_started(&self) {
        self.inner.processing_in_flight.inc();
    }

    pub fn processing_finished(&self) {
        self.inner.processing_in_flight.dec();
    }

    pub fn event_filtered(&self) {
        self.inner.events_filtered.inc();
    }

    pub fn events_persisted(&self, count: u64) {
        self.inner.events_persisted.inc_by(count);
    }

    pub fn failure(&self, stage: &str) {
        self.inner.failures.with_label_values(&[stage]).inc();
    }

    pub fn clickhouse_queued(&self) {
        self.inner.clickhouse_queue_depth.inc();
    }

    pub fn clickhouse_dequeued(&self) {
        self.inner.clickhouse_queue_depth.dec();
    }

    pub fn observe_clickhouse_batch(&self, rows: usize, duration_seconds: f64) {
        self.inner.clickhouse_batch_rows.observe(rows as f64);
        self.inner
            .clickhouse_batch_duration_seconds
            .observe(duration_seconds);
    }

    pub fn clickhouse_insert_retried(&self) {
        self.inner.clickhouse_insert_retries.inc();
    }

    pub fn encode(&self) -> Result<(Vec<u8>, String), prometheus::Error> {
        let encoder = TextEncoder::new();
        let mut body = Vec::new();
        encoder.encode(&self.inner.registry.gather(), &mut body)?;
        Ok((body, encoder.format_type().to_string()))
    }
}

fn register_counter(
    registry: &Registry,
    name: &str,
    help: &str,
) -> Result<IntCounter, prometheus::Error> {
    let counter = IntCounter::with_opts(Opts::new(name, help))?;
    registry.register(Box::new(counter.clone()))?;
    Ok(counter)
}

fn register_gauge(
    registry: &Registry,
    name: &str,
    help: &str,
) -> Result<IntGauge, prometheus::Error> {
    let gauge = IntGauge::with_opts(Opts::new(name, help))?;
    registry.register(Box::new(gauge.clone()))?;
    Ok(gauge)
}

async fn render_metrics(State(metrics): State<Metrics>) -> Response {
    match metrics.encode() {
        Ok((body, content_type)) => ([(header::CONTENT_TYPE, content_type)], body).into_response(),
        Err(error) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("failed to encode metrics: {error}"),
        )
            .into_response(),
    }
}

pub async fn serve(listener: tokio::net::TcpListener, metrics: Metrics) -> Result<()> {
    let address: SocketAddr = listener.local_addr()?;
    let app = Router::new()
        .route("/metrics", get(render_metrics))
        .with_state(metrics);
    info!("log ingestor Prometheus metrics listening on http://{address}/metrics");
    axum::serve(listener, app).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::Metrics;

    #[test]
    fn encodes_ingestion_and_process_metrics() {
        let metrics = Metrics::new().expect("metrics registry");
        metrics.kafka_message_received();
        metrics.events_persisted(2);
        metrics.failure("clickhouse_insert");

        let (body, content_type) = metrics.encode().expect("metrics encoding");
        let body = String::from_utf8(body).expect("UTF-8 metrics");

        assert!(content_type.starts_with("text/plain"));
        assert!(body.contains("netai_log_ingestor_kafka_messages_received_total 1"));
        assert!(body.contains("netai_log_ingestor_events_persisted_total 2"));
        assert!(body.contains("netai_log_ingestor_failures_total{stage=\"clickhouse_insert\"} 1"));
        assert!(body.contains("process_cpu_seconds_total"));
    }
}
