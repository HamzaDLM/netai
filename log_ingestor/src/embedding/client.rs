use anyhow::{Context, Result, bail};
use reqwest::Client;
use serde_json::{Value, json};
use std::time::Duration;

use crate::config::Config;

pub struct EmbeddingClient {
    http: Client,
    url: String,
    model: String,
    api_key: Option<String>,
    dimension: u64,
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
        }
    }

    pub fn dimension(&self) -> u64 {
        self.dimension
    }

    pub async fn embed(&self, text: &str) -> Result<Vec<f32>> {
        let body = json!({
            "model": self.model,
            "input": text,
        });

        let mut req = self.http.post(&self.url).json(&body);
        if let Some(key) = &self.api_key {
            req = req.bearer_auth(key);
        }

        let response: Value = req
            .send()
            .await
            .context("failed to send embedding request")?
            .error_for_status()
            .context("embedding endpoint returned a non-success status")?
            .json()
            .await
            .context("failed to parse embedding response as JSON")?;

        let vector = extract_embedding(&response).context("failed to extract embedding vector")?;
        if vector.len() != self.dimension as usize {
            bail!(
                "embedding length mismatch: got {}, expected {}",
                vector.len(),
                self.dimension
            );
        }

        Ok(vector)
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
