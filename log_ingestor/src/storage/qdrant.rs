use crate::types::QdrantPoint;
use anyhow::{Context, Result, bail};
use log::debug;
use reqwest::Client;
use serde_json::json;
use uuid::Uuid;

pub async fn ensure_collection_exists(
    client: &Client,
    url: &str,
    collection: &str,
    vector_size: u64,
) -> Result<()> {
    debug!("ensuring collection {} exists", collection);

    let res = client
        .get(&format!("{}/collections/{}", url, collection))
        .send()
        .await?;

    if res.status() == 404 {
        client
            .put(&format!("{}/collections/{}", url, collection))
            .json(&json!({
                "vectors": { "size": vector_size, "distance": "Cosine" }
            }))
            .send()
            .await?
            .error_for_status()?;
        return Ok(());
    }

    let body: serde_json::Value = res.error_for_status()?.json().await?;
    let existing_size = body
        .get("result")
        .and_then(|r| r.get("config"))
        .and_then(|c| c.get("params"))
        .and_then(|p| p.get("vectors"))
        .and_then(|v| v.get("size"))
        .and_then(|s| s.as_u64())
        .context("could not read existing collection vector size from Qdrant response")?;

    if existing_size != vector_size {
        bail!(
            "Qdrant collection '{}' has vector size {}, but embedder produces {}. Recreate the collection or update dimension.",
            collection,
            existing_size,
            vector_size
        );
    }

    Ok(())
}

pub async fn upsert_point(
    client: &Client,
    base_url: &str,
    collection: &str,
    id: Uuid,
    vector: Vec<f32>,
    template: &str,
    vendor: &str,
    dedup_key: &str,
) -> Result<()> {
    let point = QdrantPoint {
        id,
        vector,
        payload: json!({
            "template": template,
            "vendor": vendor,
            "dedup_key": dedup_key
        }),
    };

    let url = format!("{}/collections/{}/points?wait=true", base_url, collection);
    debug!("upserting {} in collection {}", template, collection);

    client
        .put(&url)
        .json(&json!({ "points": [point] }))
        .send()
        .await?
        .error_for_status()?;

    Ok(())
}

pub async fn fetch_existing_templates(
    client: &Client,
    base_url: &str,
    collection: &str,
) -> Result<Vec<String>> {
    let url = format!("{}/collections/{}/points/scroll", base_url, collection);
    let mut templates = Vec::new();
    let mut offset: Option<serde_json::Value> = None;

    loop {
        let mut body = json!({
            "limit": 256,
            "with_payload": true,
            "with_vector": false,
        });

        if let Some(current_offset) = &offset {
            body["offset"] = current_offset.clone();
        }

        let res: serde_json::Value = client
            .post(&url)
            .json(&body)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;

        let points = res
            .get("result")
            .and_then(|r| r.get("points"))
            .and_then(|p| p.as_array())
            .context("invalid Qdrant scroll response: missing result.points")?;

        for point in points {
            if let Some(dedup_key) = point
                .get("payload")
                .and_then(|p| p.get("dedup_key"))
                .and_then(|t| t.as_str())
            {
                templates.push(dedup_key.to_string());
                continue;
            }

            if let Some(template) = point
                .get("payload")
                .and_then(|p| p.get("template"))
                .and_then(|t| t.as_str())
            {
                templates.push(format!("unknown::{template}"));
            }
        }

        offset = res
            .get("result")
            .and_then(|r| r.get("next_page_offset"))
            .cloned()
            .filter(|value| !value.is_null());

        if offset.is_none() {
            break;
        }
    }

    Ok(templates)
}
