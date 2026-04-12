use std::sync::Arc;

use dashmap::DashMap;
use log::{debug, info, warn};
use redis::AsyncCommands;
use reqwest::Client;
use serde::Deserialize;

use crate::config::Config;

#[derive(Debug, Clone, Deserialize)]
pub struct VendorLookupItem {
    pub ip: String,
    pub hostname: String,
    pub vendor: String,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum VendorLookupResponse {
    List(Vec<VendorLookupItem>),
    Wrapped { items: Vec<VendorLookupItem> },
}

pub struct VendorCache {
    config: Arc<Config>,
    redis_client: Option<redis::Client>,
    by_hostname: DashMap<String, String>,
    by_ip: DashMap<String, String>,
}

impl VendorCache {
    pub fn new(config: Arc<Config>) -> Self {
        let redis_client =
            config
                .redis_url
                .as_ref()
                .and_then(|url| match redis::Client::open(url.as_str()) {
                    Ok(client) => Some(client),
                    Err(err) => {
                        warn!("invalid REDIS_URL; falling back to in-memory cache: {err}");
                        None
                    }
                });

        if redis_client.is_some() {
            info!("vendor cache configured with Redis (with in-memory fallback)");
        } else {
            info!("vendor cache running in in-memory mode");
        }

        Self {
            config,
            redis_client,
            by_hostname: DashMap::new(),
            by_ip: DashMap::new(),
        }
    }

    pub async fn warmup(&self, http: &Client) {
        let Some(url) = self.config.vendor_lookup_url.as_ref() else {
            debug!("VENDOR_LOOKUP_URL is unset; vendor cache warmup skipped");
            return;
        };

        let response = match http.get(url).send().await {
            Ok(response) => response,
            Err(err) => {
                warn!("vendor warmup API call failed: {err}");
                return;
            }
        };

        let payload = match response.json::<VendorLookupResponse>().await {
            Ok(payload) => payload,
            Err(err) => {
                warn!("vendor warmup response decode failed: {err}");
                return;
            }
        };

        let items = match payload {
            VendorLookupResponse::List(items) => items,
            VendorLookupResponse::Wrapped { items } => items,
        };

        if items.is_empty() {
            debug!("vendor warmup returned 0 entries");
            return;
        }

        self.store_in_memory(&items);

        if let Some(redis) = &self.redis_client {
            match redis.get_multiplexed_tokio_connection().await {
                Ok(mut conn) => {
                    for item in &items {
                        let vendor = item.vendor.trim().to_lowercase();
                        if vendor.is_empty() {
                            continue;
                        }

                        let hostname = item.hostname.trim().to_lowercase();
                        if !hostname.is_empty() {
                            let key = self.hostname_key(&hostname);
                            if let Err(err) = conn.set::<_, _, ()>(key, &vendor).await {
                                warn!("redis hostname cache set failed: {err}");
                            }
                        }

                        let ip = item.ip.trim();
                        if !ip.is_empty() {
                            let key = self.ip_key(ip);
                            if let Err(err) = conn.set::<_, _, ()>(key, &vendor).await {
                                warn!("redis ip cache set failed: {err}");
                            }
                        }
                    }
                }
                Err(err) => {
                    warn!("redis unavailable during vendor warmup, using in-memory cache: {err}");
                }
            }
        }

        debug!("vendor warmup loaded {} entries", items.len());
    }

    pub async fn resolve_vendor(&self, hostname: &str, ip: Option<&str>) -> Option<String> {
        let hostname_key = hostname.trim().to_lowercase();

        if let Some(redis) = &self.redis_client {
            match redis.get_multiplexed_tokio_connection().await {
                Ok(mut conn) => {
                    if !hostname_key.is_empty() {
                        let redis_key = self.hostname_key(&hostname_key);
                        match conn.get::<_, Option<String>>(redis_key).await {
                            Ok(Some(vendor)) if !vendor.trim().is_empty() => {
                                return Some(vendor);
                            }
                            Ok(_) => {}
                            Err(err) => warn!("redis hostname lookup failed: {err}"),
                        }
                    }

                    if let Some(ip) = ip.filter(|value| !value.trim().is_empty()) {
                        let redis_key = self.ip_key(ip);
                        match conn.get::<_, Option<String>>(redis_key).await {
                            Ok(Some(vendor)) if !vendor.trim().is_empty() => {
                                return Some(vendor);
                            }
                            Ok(_) => {}
                            Err(err) => warn!("redis ip lookup failed: {err}"),
                        }
                    }
                }
                Err(err) => {
                    warn!("redis unavailable for vendor lookup, using in-memory cache: {err}");
                }
            }
        }

        if !hostname_key.is_empty() {
            if let Some(vendor) = self.by_hostname.get(&hostname_key) {
                return Some(vendor.clone());
            }
        }

        if let Some(ip) = ip {
            if let Some(vendor) = self.by_ip.get(ip) {
                return Some(vendor.clone());
            }
        }

        None
    }

    fn hostname_key(&self, hostname: &str) -> String {
        format!("{}:hostname:{}", self.config.vendor_cache_prefix, hostname)
    }

    fn ip_key(&self, ip: &str) -> String {
        format!("{}:ip:{}", self.config.vendor_cache_prefix, ip)
    }

    fn store_in_memory(&self, items: &[VendorLookupItem]) {
        for item in items {
            let vendor = item.vendor.trim().to_lowercase();
            if vendor.is_empty() {
                continue;
            }

            let hostname = item.hostname.trim().to_lowercase();
            if !hostname.is_empty() {
                self.by_hostname.insert(hostname, vendor.clone());
            }

            let ip = item.ip.trim().to_string();
            if !ip.is_empty() {
                self.by_ip.insert(ip, vendor.clone());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{VendorCache, VendorLookupItem, VendorLookupResponse};
    use crate::config::Config;
    use std::sync::Arc;

    fn test_config(vendor_lookup_url: Option<String>) -> Arc<Config> {
        let mut config = Config::from_env();
        config.redis_url = None;
        config.vendor_lookup_url = vendor_lookup_url;
        config.vendor_cache_prefix = "vendor_cache_test".to_string();
        Arc::new(config)
    }

    #[tokio::test]
    async fn stores_entries_in_memory_cache() {
        let cache = VendorCache::new(test_config(None));
        cache.store_in_memory(&[VendorLookupItem {
            ip: "10.0.0.1".to_string(),
            hostname: "EDGE-FW-01".to_string(),
            vendor: "Fortinet".to_string(),
        }]);

        assert_eq!(
            cache.resolve_vendor("edge-fw-01", None).await.as_deref(),
            Some("fortinet")
        );
        assert_eq!(
            cache
                .resolve_vendor("unknown-host", Some("10.0.0.1"))
                .await
                .as_deref(),
            Some("fortinet")
        );
    }

    #[test]
    fn decodes_list_payload_shape() {
        let payload: VendorLookupResponse = serde_json::from_str(
            r#"[{"ip":"10.0.0.1","hostname":"edge-fw-01","vendor":"fortinet"}]"#,
        )
        .expect("decode list payload");
        let items = match payload {
            VendorLookupResponse::List(items) => items,
            VendorLookupResponse::Wrapped { items } => items,
        };
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].vendor, "fortinet");
    }

    #[test]
    fn decodes_wrapped_payload_shape() {
        let payload: VendorLookupResponse = serde_json::from_str(
            r#"{"items":[{"ip":"192.0.2.5","hostname":"arista-leaf-1","vendor":"Arista"}]}"#,
        )
        .expect("decode wrapped payload");
        let items = match payload {
            VendorLookupResponse::List(items) => items,
            VendorLookupResponse::Wrapped { items } => items,
        };
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].hostname, "arista-leaf-1");
    }

    #[test]
    fn invalid_payload_decode_returns_error() {
        let payload = serde_json::from_str::<VendorLookupResponse>(r#"{"bad":"payload"}"#);
        assert!(payload.is_err());
    }
}
