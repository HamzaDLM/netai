mod config;
mod embedding;
mod kafka;
mod pipeline;
mod processing;
mod serde_helpers;
mod storage;
mod types;

use anyhow::Result;
use config::Config;
use kafka::consumer::start_consumer;
use kafka::lag::print_lag_periodically;
use log::error;
use pipeline::Pipeline;
use std::sync::Arc;

use crate::kafka::consumer::create_stream_consumer;

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
