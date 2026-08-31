use std::{
    collections::{BTreeSet, HashMap},
    future::Future,
};

use anyhow::{Context, Result, bail};
use futures::{FutureExt, StreamExt, future::BoxFuture, stream::FuturesUnordered};
use log::warn;
use rdkafka::{
    ClientConfig, Message,
    consumer::{CommitMode, Consumer, StreamConsumer},
};
use tokio::time::{Duration, sleep};

use crate::{metrics::Metrics, types::IncomingSyslog};

const PAYLOAD_PREVIEW_BYTES: usize = 256;

pub fn create_stream_consumer(brokers: &str, group_id: &str) -> Result<StreamConsumer> {
    let consumer: StreamConsumer = ClientConfig::new()
        .set("group.id", group_id)
        .set("bootstrap.servers", brokers)
        .set("enable.partition.eof", "false")
        .set("auto.offset.reset", "latest")
        .set("enable.auto.commit", "true")
        .set("enable.auto.offset.store", "false")
        .set("auto.commit.interval.ms", "1000")
        .create()?;
    Ok(consumer)
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct PartitionKey {
    topic: String,
    partition: i32,
}

#[derive(Clone, Debug)]
struct KafkaPosition {
    key: PartitionKey,
    offset: i64,
}

struct ProcessingOutcome {
    position: KafkaPosition,
    result: Result<()>,
}

#[derive(Debug)]
struct PartitionProgress {
    next_offset: i64,
    completed: BTreeSet<i64>,
}

#[derive(Default)]
struct OffsetTracker {
    partitions: HashMap<PartitionKey, PartitionProgress>,
}

impl OffsetTracker {
    fn register(&mut self, position: &KafkaPosition) {
        self.partitions
            .entry(position.key.clone())
            .or_insert_with(|| PartitionProgress {
                next_offset: position.offset,
                completed: BTreeSet::new(),
            });
    }

    fn complete(&mut self, position: &KafkaPosition) -> Option<(i64, u64)> {
        let progress = self.partitions.get_mut(&position.key)?;
        if position.offset < progress.next_offset {
            return None;
        }
        progress.completed.insert(position.offset);

        let mut advanced = 0u64;
        while progress.completed.remove(&progress.next_offset) {
            progress.next_offset = progress.next_offset.saturating_add(1);
            advanced += 1;
        }
        (advanced > 0).then_some((progress.next_offset, advanced))
    }
}

pub async fn start_consumer<F, Fut>(
    brokers: &str,
    topic: &str,
    group_id: &str,
    max_in_flight: usize,
    metrics: Metrics,
    handler: F,
) -> Result<()>
where
    F: Fn(IncomingSyslog) -> Fut + Send + Sync,
    Fut: Future<Output = Result<()>> + Send + 'static,
{
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
    let mut stream_open = true;
    let mut in_flight: FuturesUnordered<BoxFuture<'static, ProcessingOutcome>> =
        FuturesUnordered::new();
    let mut offsets = OffsetTracker::default();
    let max_in_flight = max_in_flight.max(1);

    while stream_open || !in_flight.is_empty() {
        if !stream_open || in_flight.len() >= max_in_flight {
            let Some(outcome) = in_flight.next().await else {
                break;
            };
            handle_processing_outcome(&consumer, &metrics, &mut offsets, outcome)?;
            continue;
        }

        tokio::select! {
            maybe_outcome = in_flight.next(), if !in_flight.is_empty() => {
                if let Some(outcome) = maybe_outcome {
                    handle_processing_outcome(&consumer, &metrics, &mut offsets, outcome)?;
                }
            }
            maybe_message = stream.next() => {
                let Some(message) = maybe_message else {
                    stream_open = false;
                    continue;
                };
                let msg = match message {
                    Ok(msg) => msg,
                    Err(err) => {
                        metrics.failure("kafka_consume");
                        warn!(
                            "kafka consume error on topic '{topic}' ({err:#}). If the topic does not exist yet, the consumer will keep retrying."
                        );
                        continue;
                    }
                };
                metrics.kafka_message_received();
                let position = KafkaPosition {
                    key: PartitionKey {
                        topic: msg.topic().to_string(),
                        partition: msg.partition(),
                    },
                    offset: msg.offset(),
                };
                offsets.register(&position);

                let Some(payload) = msg.payload() else {
                    metrics.kafka_message_without_payload();
                    store_completed_offset(&consumer, &metrics, &mut offsets, &position)?;
                    continue;
                };
                let log: IncomingSyslog = match serde_json::from_slice(payload) {
                    Ok(log) => log,
                    Err(err) => {
                        metrics.kafka_message_malformed();
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
                        store_completed_offset(&consumer, &metrics, &mut offsets, &position)?;
                        continue;
                    }
                };

                metrics.processing_started();
                let result = handler(log);
                in_flight.push(
                    async move {
                        ProcessingOutcome {
                            position,
                            result: result.await,
                        }
                    }
                    .boxed(),
                );
            }
        }
    }

    consumer
        .commit_consumer_state(CommitMode::Sync)
        .context("failed to commit final processed Kafka offsets")?;
    Ok(())
}

fn handle_processing_outcome(
    consumer: &StreamConsumer,
    metrics: &Metrics,
    offsets: &mut OffsetTracker,
    outcome: ProcessingOutcome,
) -> Result<()> {
    metrics.processing_finished();
    if let Err(error) = outcome.result {
        metrics.failure("processing");
        bail!(
            "processing failed for Kafka topic '{}' partition {} offset {}: {error:#}",
            outcome.position.key.topic,
            outcome.position.key.partition,
            outcome.position.offset,
        );
    }
    store_completed_offset(consumer, metrics, offsets, &outcome.position)
}

fn store_completed_offset(
    consumer: &StreamConsumer,
    metrics: &Metrics,
    offsets: &mut OffsetTracker,
    position: &KafkaPosition,
) -> Result<()> {
    if let Some((next_offset, count)) = offsets.complete(position) {
        consumer
            .store_offset(&position.key.topic, position.key.partition, next_offset)
            .with_context(|| {
                format!(
                    "failed to store Kafka offset for topic '{}' partition {}",
                    position.key.topic, position.key.partition
                )
            })?;
        metrics.kafka_offset_stored(count);
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

#[cfg(test)]
mod tests {
    use super::{KafkaPosition, OffsetTracker, PartitionKey};

    fn position(partition: i32, offset: i64) -> KafkaPosition {
        KafkaPosition {
            key: PartitionKey {
                topic: "syslogs".to_string(),
                partition,
            },
            offset,
        }
    }

    #[test]
    fn offsets_only_advance_after_contiguous_completion() {
        let mut tracker = OffsetTracker::default();
        for offset in 10..=12 {
            tracker.register(&position(0, offset));
        }

        assert_eq!(tracker.complete(&position(0, 11)), None);
        assert_eq!(tracker.complete(&position(0, 10)), Some((12, 2)));
        assert_eq!(tracker.complete(&position(0, 12)), Some((13, 1)));
    }

    #[test]
    fn offsets_are_tracked_independently_per_partition() {
        let mut tracker = OffsetTracker::default();
        tracker.register(&position(0, 5));
        tracker.register(&position(1, 20));

        assert_eq!(tracker.complete(&position(1, 20)), Some((21, 1)));
        assert_eq!(tracker.complete(&position(0, 5)), Some((6, 1)));
    }
}
