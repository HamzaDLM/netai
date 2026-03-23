use crate::types::IncomingSyslog;
use anyhow::Result;
use futures::StreamExt;
use rdkafka::{
    ClientConfig, Message,
    consumer::{Consumer, StreamConsumer},
};

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

    consumer.subscribe(&[topic])?;

    let mut stream = consumer.stream();

    while let Some(msg) = stream.next().await {
        let msg = msg?;
        if let Some(payload) = msg.payload() {
            let log: IncomingSyslog = serde_json::from_slice(payload)?;
            handler(log)?;
        }
    }

    Ok(())
}
