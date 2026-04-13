use anyhow::{Context, Result, bail};
use log::warn;
use reqwest::Client;
use serde_json::{Value, json};
use std::{
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::{
    sync::{Mutex, Semaphore},
    time::sleep,
};

use crate::config::Config;

pub struct EmbeddingClient {
    http: Client,
    url: String,
    model: String,
    api_key: Option<String>,
    dimension: u64,
    in_flight: Arc<Semaphore>,
    min_request_interval: Duration,
    last_request_at: Arc<Mutex<Option<Instant>>>,
    max_retries: u32,
    retry_backoff_ms: u64,
}

impl EmbeddingClient {
    pub fn new(config: &Config) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(config.embedding_timeout_secs))
            .build()
            .expect("failed to build embedding HTTP client");

        Self {
            http,
            url: config.embedding_url.clone(),
            model: config.embedding_model.clone(),
            api_key: config.embedding_api_key.clone(),
            dimension: config.embedding_dimension,
            in_flight: Arc::new(Semaphore::new(config.embedding_max_in_flight.max(1))),
            min_request_interval: requests_per_second_to_interval(
                config.embedding_max_requests_per_second,
            ),
            last_request_at: Arc::new(Mutex::new(None)),
            max_retries: config.embedding_max_retries,
            retry_backoff_ms: config.embedding_retry_backoff_ms.max(1),
        }
    }

    pub fn dimension(&self) -> u64 {
        self.dimension
    }

    pub async fn embed(&self, text: &str) -> Result<Vec<f32>> {
        let _permit = self
            .in_flight
            .acquire()
            .await
            .expect("embedding semaphore should not be closed");

        let body = json!({
            "model": self.model,
            "input": text,
        });

        for attempt in 0..=self.max_retries {
            self.throttle_request_rate().await;
            let mut req = self.http.post(&self.url).json(&body);
            if let Some(key) = &self.api_key {
                req = req.bearer_auth(key);
            }

            let response = req
                .send()
                .await
                .context("failed to send embedding request")?;
            let status = response.status();

            if status.is_success() {
                let response: Value = response
                    .json()
                    .await
                    .context("failed to parse embedding response as JSON")?;
                let vector =
                    extract_embedding(&response).context("failed to extract embedding vector")?;
                if vector.len() != self.dimension as usize {
                    bail!(
                        "embedding length mismatch: got {}, expected {}",
                        vector.len(),
                        self.dimension
                    );
                }
                return Ok(vector);
            }

            let body_preview = response.text().await.unwrap_or_default();
            if should_retry(status.as_u16()) && attempt < self.max_retries {
                let backoff = self.retry_backoff_ms * (1u64 << attempt.min(10));
                warn!(
                    "embedding request failed with status {} (attempt {}/{}). retrying in {}ms",
                    status,
                    attempt + 1,
                    self.max_retries + 1,
                    backoff
                );
                sleep(Duration::from_millis(backoff)).await;
                continue;
            }

            bail!(
                "embedding endpoint returned non-success status {}: {}",
                status,
                body_preview
            );
        }

        bail!("embedding request exhausted retries")
    }

    async fn throttle_request_rate(&self) {
        if self.min_request_interval.is_zero() {
            return;
        }

        let mut guard = self.last_request_at.lock().await;
        if let Some(last_request) = *guard {
            let elapsed = last_request.elapsed();
            if elapsed < self.min_request_interval {
                sleep(self.min_request_interval - elapsed).await;
            }
        }
        *guard = Some(Instant::now());
    }
}

fn requests_per_second_to_interval(rps: u64) -> Duration {
    if rps == 0 {
        Duration::ZERO
    } else {
        Duration::from_secs_f64(1.0 / (rps as f64))
    }
}

fn should_retry(status: u16) -> bool {
    status == 429 || (500..=599).contains(&status)
}

#[cfg(test)]
mod tests {
    use super::{extract_embedding, requests_per_second_to_interval, should_retry};
    use serde_json::json;

    #[test]
    fn should_retry_matches_expected_statuses() {
        assert!(should_retry(429));
        assert!(should_retry(500));
        assert!(should_retry(503));
        assert!(!should_retry(400));
        assert!(!should_retry(404));
    }

    #[test]
    fn requests_per_second_interval_is_zero_when_disabled() {
        assert!(requests_per_second_to_interval(0).is_zero());
    }

    #[test]
    fn requests_per_second_interval_is_calculated_when_enabled() {
        let interval = requests_per_second_to_interval(4);
        assert_eq!(interval.as_millis(), 250);
    }

    #[test]
    fn extract_embedding_reads_openai_shape() {
        let payload = json!({
            "data": [
                { "embedding": [0.1, 0.2, 0.3] }
            ]
        });
        let vector = extract_embedding(&payload).expect("extract vector");
        assert_eq!(vector, vec![0.1, 0.2, 0.3]);
    }

    #[test]
    fn extract_embedding_reads_fallback_shape() {
        let payload = json!({
            "result": {
                "embedding": [1.0, 2.0]
            }
        });
        let vector = extract_embedding(&payload).expect("extract vector");
        assert_eq!(vector, vec![1.0, 2.0]);
    }

    #[test]
    fn extract_embedding_fails_for_missing_array() {
        let payload = json!({ "data": [] });
        assert!(extract_embedding(&payload).is_err());
    }
}

fn extract_embedding(payload: &Value) -> Result<Vec<f32>> {
    let candidates = [
        payload.pointer("/data/0/embedding"),
        payload.pointer("/embedding"),
        payload.pointer("/result/embedding"),
    ];

    for candidate in candidates.into_iter().flatten() {
        if let Some(array) = candidate.as_array() {
            let mut out = Vec::with_capacity(array.len());
            for item in array {
                let v = item.as_f64().context("embedding element is not a number")? as f32;
                out.push(v);
            }
            return Ok(out);
        }
    }

    bail!(
        "embedding response does not contain an embedding array in /data/0/embedding, /embedding, or /result/embedding"
    )
}
