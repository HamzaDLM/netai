use std::{collections::HashMap, sync::Arc, time::Instant};

use anyhow::{Result, anyhow};
use log::{debug, warn};
use rdkafka::{
    consumer::Consumer,
    topic_partition_list::{Offset, TopicPartitionList},
};
use tokio::time::{Duration, sleep};

use crate::metrics::Metrics;

struct LagMeasurement {
    partition: i32,
    committed_offset: i64,
    lag: i64,
}

pub async fn observe_lag_periodically<C>(
    consumer: Arc<C>,
    topic: String,
    poll_interval: Duration,
    metrics: Metrics,
) where
    C: Consumer + Send + Sync + 'static,
{
    let mut previous: HashMap<i32, (i64, Instant)> = HashMap::new();

    loop {
        let observed_consumer = consumer.clone();
        let observed_topic = topic.clone();
        match tokio::task::spawn_blocking(move || {
            collect_lag(observed_consumer.as_ref(), &observed_topic)
        })
        .await
        {
            Ok(Ok(measurements)) => {
                let now = Instant::now();
                for measurement in measurements {
                    let processed_per_second = previous
                        .get(&measurement.partition)
                        .map(|(previous_offset, previous_time)| {
                            let offset_delta =
                                (measurement.committed_offset - *previous_offset).max(0) as f64;
                            let seconds = now.duration_since(*previous_time).as_secs_f64();
                            if seconds > 0.0 {
                                offset_delta / seconds
                            } else {
                                0.0
                            }
                        })
                        .unwrap_or_default();
                    previous.insert(measurement.partition, (measurement.committed_offset, now));
                    let partition = measurement.partition.to_string();
                    metrics.observe_kafka_partition(
                        &topic,
                        &partition,
                        measurement.lag,
                        processed_per_second,
                    );
                    debug!(
                        "kafka partition {} lag: {}, committed messages/s: {:.2}",
                        measurement.partition, measurement.lag, processed_per_second
                    );
                }
            }
            Ok(Err(error)) => {
                metrics.failure("kafka_lag_observation");
                warn!("failed to observe Kafka lag: {error:#}");
            }
            Err(error) => {
                metrics.failure("kafka_lag_observation");
                warn!("kafka lag observation task failed: {error}");
            }
        }

        sleep(poll_interval.max(Duration::from_secs(1))).await;
    }
}

fn collect_lag(consumer: &impl Consumer, topic: &str) -> Result<Vec<LagMeasurement>> {
    let timeout = std::time::Duration::from_secs(1);
    let metadata = consumer.fetch_metadata(Some(topic), timeout)?;
    let topic_metadata = metadata
        .topics()
        .iter()
        .find(|candidate| candidate.name() == topic)
        .ok_or_else(|| anyhow!("Kafka metadata did not include topic '{topic}'"))?;
    let partitions = topic_metadata
        .partitions()
        .iter()
        .map(|partition| partition.id())
        .collect::<Vec<_>>();

    let mut requested_offsets = TopicPartitionList::new();
    for partition in &partitions {
        requested_offsets.add_partition(topic, *partition);
    }
    let committed = consumer.committed_offsets(requested_offsets, timeout)?;

    partitions
        .into_iter()
        .map(|partition| {
            let (_, high) = consumer.fetch_watermarks(topic, partition, timeout)?;
            let committed_offset = committed
                .find_partition(topic, partition)
                .map(|element| match element.offset() {
                    Offset::Offset(offset) if offset >= 0 => offset,
                    _ => 0,
                })
                .unwrap_or_default();
            Ok(LagMeasurement {
                partition,
                committed_offset,
                lag: (high - committed_offset).max(0),
            })
        })
        .collect()
}
