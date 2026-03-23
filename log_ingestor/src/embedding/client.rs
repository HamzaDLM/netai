use anyhow::Result;
use std::hash::{Hash, Hasher};
use std::collections::hash_map::DefaultHasher;

pub struct EmbeddingClient;

impl EmbeddingClient {
    pub const DIMENSION: u64 = 32;

    pub fn new() -> Self {
        Self
    }

    pub async fn embed(&self, text: &str) -> Result<Vec<f32>> {
        // Deterministic fake embedding (MVP)
        let mut hasher = DefaultHasher::new();
        text.hash(&mut hasher);
        let hash = hasher.finish();

        let mut vec = Vec::with_capacity(Self::DIMENSION as usize);
        for i in 0..Self::DIMENSION {
            vec.push(((hash >> i) & 1) as f32);
        }

        Ok(vec)
    }
}
