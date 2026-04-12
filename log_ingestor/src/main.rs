use anyhow::Result;
use log::error;
use log_ingestor::config::Config;
use log_ingestor::kafka::consumer::start_consumer;
use log_ingestor::kafka::lag::print_lag_periodically;
use log_ingestor::pipeline::Pipeline;
use std::sync::Arc;
use tokio::time::{self, Duration};

use log_ingestor::kafka::consumer::create_stream_consumer;

#[tokio::main]
async fn main() -> Result<()> {
    let _ = dotenvy::dotenv();
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(
        if cfg!(debug_assertions) {
            "debug"
        } else {
            "info"
        },
    ))
    .init();
    let config = Arc::new(Config::from_env());
    let pipeline = Arc::new(Pipeline::new(config.clone()));

    // Ensure collection exists before consuming
    pipeline.ensure_collection().await?;
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
    let consumer = create_stream_consumer(&config.kafka_brokers, &config.kafka_group_id)?;
    let topic = config.kafka_topic.to_string();
    tokio::spawn(async move {
        let _ = print_lag_periodically(consumer, &topic, vec![0]).await;
    });

    // process the logs
    let pipeline_clone = pipeline.clone();
    start_consumer(
        &config.kafka_brokers,
        &config.kafka_topic,
        &config.kafka_group_id,
        move |log| {
            let pipeline_clone = pipeline_clone.clone();
            tokio::spawn(async move {
                if let Err(err) = pipeline_clone.process(log).await {
                    error!("pipeline processing error: {err:#}");
                }
            });
            Ok(())
        },
    )
    .await?;

    Ok(())
}
