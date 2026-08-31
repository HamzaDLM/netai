use anyhow::Result;
use log_ingestor::config::Config;
use log_ingestor::kafka::consumer::start_consumer;
use log_ingestor::kafka::lag::observe_lag_periodically;
use log_ingestor::metrics::{self, Metrics};
use log_ingestor::pipeline::Pipeline;
use std::sync::Arc;
use tokio::time::{self, Duration};

use log_ingestor::kafka::consumer::create_stream_consumer;

#[tokio::main]
async fn main() -> Result<()> {
    let _ = dotenvy::from_filename(".env").or_else(|_| dotenvy::from_filename("log_ingestor/.env"));
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(
        if cfg!(debug_assertions) {
            "debug"
        } else {
            "info"
        },
    ))
    .init();
    let config = Arc::new(Config::from_env());
    let metrics = Metrics::new()?;
    let metrics_listener = tokio::net::TcpListener::bind(&config.metrics_bind).await?;
    let pipeline = Arc::new(Pipeline::new(config.clone(), metrics.clone()));

    // Ensure storage exists before consuming.
    pipeline.ensure_storage().await?;
    pipeline.refresh_vendor_cache().await;

    // Refresh vendor lookup cache periodically; never fail ingestion on warmup issues.
    let refresh_pipeline = pipeline.clone();
    let refresh_interval = Duration::from_secs(config.vendor_refresh_secs.max(30));
    tokio::spawn(async move {
        let mut ticker = time::interval(refresh_interval);
        loop {
            ticker.tick().await;
            refresh_pipeline.refresh_vendor_cache().await;
        }
    });

    // spawn the lag printer task
    let consumer = Arc::new(create_stream_consumer(
        &config.kafka_brokers,
        &config.kafka_group_id,
    )?);
    let topic = config.kafka_topic.to_string();
    let lag_metrics = metrics.clone();
    let lag_interval = Duration::from_secs(config.kafka_lag_poll_interval_secs.max(1));
    tokio::spawn(async move {
        observe_lag_periodically(consumer, topic, lag_interval, lag_metrics).await;
    });

    // Processing completion includes ClickHouse persistence, so the bounded in-flight
    // set applies backpressure all the way to Kafka and offsets remain replayable.
    let pipeline_clone = pipeline.clone();
    let ingestion = start_consumer(
        &config.kafka_brokers,
        &config.kafka_topic,
        &config.kafka_group_id,
        config.ingest_max_in_flight,
        metrics.clone(),
        move |log| {
            let pipeline_clone = pipeline_clone.clone();
            async move { pipeline_clone.process(log).await }
        },
    );
    let metrics_server = metrics::serve(metrics_listener, metrics);

    tokio::select! {
        result = ingestion => result,
        result = metrics_server => result,
    }
}
