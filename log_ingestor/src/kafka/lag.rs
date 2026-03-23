use anyhow::Result;
use log::debug;
use rdkafka::consumer::Consumer;
use rdkafka::topic_partition_list::Offset;
use rdkafka::topic_partition_list::TopicPartitionList;
use std::collections::HashMap;
use std::time::Instant;
use tokio::time::{Duration, sleep};

fn get_committed_offset(consumer: &impl Consumer, partition: i32, topic: &str) -> Result<i64> {
    let mut tpl = TopicPartitionList::new();
    tpl.add_partition(topic, partition);

    let committed = consumer.committed_offsets(tpl, std::time::Duration::from_secs(1))?;

    for elem in committed.elements() {
        if elem.topic() == topic && elem.partition() == partition {
            return Ok(match elem.offset() {
                Offset::Offset(v) if v >= 0 => v,
                _ => 0,
            });
        }
    }

    Ok(0)
}

pub async fn print_lag_periodically<C: Consumer + Send + Sync + 'static>(
    consumer: C,
    topic: &str,
    partitions: Vec<i32>,
) -> Result<()> {
    let mut prev_committed: HashMap<i32, (i64, Instant)> = HashMap::new();

    loop {
        for &partition in &partitions {
            let (_, high) =
                consumer.fetch_watermarks(topic, partition, std::time::Duration::from_secs(1))?;
            let committed_offset = get_committed_offset(&consumer, partition, topic)?;
            let lag = (high - committed_offset).max(0);
            let now = Instant::now();

            let processed_per_sec =
                if let Some((prev_offset, prev_ts)) = prev_committed.get(&partition) {
                    let offset_delta = (committed_offset - *prev_offset).max(0) as f64;
                    let secs = now.duration_since(*prev_ts).as_secs_f64();
                    if secs > 0.0 { offset_delta / secs } else { 0.0 }
                } else {
                    0.0
                };

            prev_committed.insert(partition, (committed_offset, now));

            debug!(
                "Partition {} lag: {}, processed/s: {:.2}",
                partition, lag, processed_per_sec
            );
        }

        sleep(Duration::from_secs(1)).await; // wait 5 seconds
    }
}
