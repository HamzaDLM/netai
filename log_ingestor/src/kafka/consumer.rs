use crate::types::IncomingSyslog;
use anyhow::Result;
use futures::StreamExt;
use log::warn;
use rdkafka::{
    ClientConfig, Message,
    consumer::{Consumer, StreamConsumer},
};
use tokio::time::{Duration, sleep};

pub fn create_stream_consumer(brokers: &str, group_id: &str) -> Result<StreamConsumer> {
    let consumer: StreamConsumer = ClientConfig::new()
        .set("group.id", group_id)
        .set("bootstrap.servers", brokers)
        .set("enable.partition.eof", "false")
        .set("auto.offset.reset", "earliest")
        .set("enable.auto.commit", "true")
        .set("auto.commit.interval.ms", "1000")
        .create()?;
    Ok(consumer)
}

pub async fn start_consumer(
    brokers: &str,
    topic: &str,
    group_id: &str,
    mut handler: impl FnMut(IncomingSyslog) -> Result<()> + Send + 'static,
) -> Result<()> {
    let consumer: StreamConsumer = create_stream_consumer(brokers, group_id)?;

    loop {
        if let Err(err) = consumer.subscribe(&[topic]) {
            warn!("failed to subscribe to Kafka topic '{topic}' ({err:#}); retrying in 5s");
            sleep(Duration::from_secs(5)).await;
            continue;
        }
        break;
    }

    let mut stream = consumer.stream();

    while let Some(msg) = stream.next().await {
        let msg = match msg {
            Ok(msg) => msg,
            Err(err) => {
                warn!(
                    "Kafka consume error on topic '{topic}' ({err:#}). If the topic does not exist yet, the consumer will keep retrying."
                );
                continue;
            }
        };
        if let Some(payload) = msg.payload() {
            let log: IncomingSyslog = match serde_json::from_slice(payload) {
                Ok(log) => log,
                Err(err) => {
                    warn!("dropping malformed Kafka payload on topic '{topic}': {err:#}");
                    continue;
                }
            };

            if let Err(err) = handler(log) {
                warn!("handler error while processing Kafka message on '{topic}': {err:#}");
            }
        }
    }

    Ok(())
}
