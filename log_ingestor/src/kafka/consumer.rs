use crate::types::IncomingSyslog;
use anyhow::Result;
use futures::StreamExt;
use log::warn;
use rdkafka::{
    ClientConfig, Message,
    consumer::{Consumer, StreamConsumer},
};
use tokio::time::{Duration, sleep};

const PAYLOAD_PREVIEW_BYTES: usize = 256;

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
                    let utf8_preview = utf8_preview(payload, PAYLOAD_PREVIEW_BYTES);
                    let hex_preview = hex_preview(payload, PAYLOAD_PREVIEW_BYTES);
                    warn!(
                        "dropping malformed Kafka payload on topic '{topic}' \
                         (partition={}, offset={}, key_len={}, payload_len={}): {err:#}; \
                         payload_utf8_preview={utf8_preview:?}; payload_hex_preview=\"{hex_preview}\"",
                        msg.partition(),
                        msg.offset(),
                        msg.key().map_or(0, |key| key.len()),
                        payload.len()
                    );
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

fn utf8_preview(bytes: &[u8], max_bytes: usize) -> String {
    let end = bytes.len().min(max_bytes);
    let mut s = String::from_utf8_lossy(&bytes[..end]).to_string();
    if bytes.len() > max_bytes {
        s.push_str(" …<truncated>");
    }
    s
}

fn hex_preview(bytes: &[u8], max_bytes: usize) -> String {
    let end = bytes.len().min(max_bytes);
    let mut out = bytes[..end]
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ");
    if bytes.len() > max_bytes {
        out.push_str(" …<truncated>");
    }
    out
}
