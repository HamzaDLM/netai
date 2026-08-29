use anyhow::{Result, bail};
use clickhouse::{Client, Row};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{
    config::Config,
    storage::clickhouse::{SyslogEventRow, build_client},
};

pub const DEFAULT_RESULT_LIMIT: u32 = 40;

#[derive(Clone)]
pub struct LogQueryService {
    client: Client,
    default_window_secs: u64,
    max_window_secs: u64,
    max_results: u32,
    timeout_secs: u64,
}

#[derive(Clone, Debug, Deserialize, JsonSchema)]
pub struct DeviceEventsRequest {
    #[schemars(description = "Device hostname, matched case-insensitively.")]
    pub hostname: String,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to one hour ago.")]
    pub start_time_unix: Option<i64>,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to now.")]
    pub end_time_unix: Option<i64>,
    #[schemars(description = "Optional syslog severity from -1 (unknown) through 7.")]
    pub severity: Option<i16>,
    #[schemars(description = "Optional case-insensitive text in raw or normalized message.")]
    pub text: Option<String>,
    #[schemars(description = "Maximum events to return; the service enforces a hard cap.")]
    pub limit: Option<u32>,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct DeviceEventsResponse {
    pub hostname: String,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub as_of_unix: i64,
    pub count: usize,
    pub truncated: bool,
    pub events: Vec<SyslogEventRow>,
}

#[derive(Clone, Debug, Deserialize, JsonSchema)]
pub struct DeviceWindowRequest {
    #[schemars(description = "Device hostname, matched case-insensitively.")]
    pub hostname: String,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to one hour ago.")]
    pub start_time_unix: Option<i64>,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to now.")]
    pub end_time_unix: Option<i64>,
}

#[derive(Clone, Debug, Deserialize, JsonSchema, Row, Serialize)]
pub struct SeverityCount {
    pub severity: i16,
    pub count: u64,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct SeveritySummaryResponse {
    pub hostname: String,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub as_of_unix: i64,
    pub total: u64,
    pub severities: Vec<SeverityCount>,
}

#[derive(Clone, Debug, Deserialize, JsonSchema)]
pub struct DevicePatternsRequest {
    #[schemars(description = "Device hostname, matched case-insensitively.")]
    pub hostname: String,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to one hour ago.")]
    pub start_time_unix: Option<i64>,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to now.")]
    pub end_time_unix: Option<i64>,
    #[schemars(description = "Maximum patterns to return; the service enforces a hard cap.")]
    pub limit: Option<u32>,
}

#[derive(Clone, Debug, Deserialize, JsonSchema, Row, Serialize)]
pub struct LogPattern {
    pub template: String,
    pub count: u64,
    pub last_seen_unix: i64,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct DevicePatternsResponse {
    pub hostname: String,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub as_of_unix: i64,
    pub count: usize,
    pub truncated: bool,
    pub patterns: Vec<LogPattern>,
}

impl LogQueryService {
    pub fn from_config(config: &Config) -> Self {
        Self {
            client: build_client(
                &config.clickhouse_url,
                &config.clickhouse_db,
                &config.clickhouse_user,
                &config.clickhouse_password,
            ),
            default_window_secs: config.log_query_default_window_secs.max(1),
            max_window_secs: config.log_query_max_window_secs.max(1),
            max_results: config.log_query_max_results.max(1),
            timeout_secs: config.log_query_timeout_secs.max(1),
        }
    }

    pub async fn health(&self) -> Result<()> {
        let value = self
            .client
            .query("SELECT 1")
            .with_option("max_execution_time", self.timeout_secs.to_string())
            .fetch_one::<u8>()
            .await?;
        if value != 1 {
            bail!("unexpected ClickHouse health response");
        }
        Ok(())
    }

    pub async fn device_events(
        &self,
        request: DeviceEventsRequest,
    ) -> Result<DeviceEventsResponse> {
        let hostname = validate_hostname(&request.hostname)?;
        let (start, end, as_of) =
            self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        if let Some(severity) = request.severity
            && !(-1..=7).contains(&severity)
        {
            bail!("severity must be between -1 and 7");
        }
        let requested_limit = request.limit.unwrap_or(DEFAULT_RESULT_LIMIT);
        let limit = requested_limit.clamp(1, self.max_results);
        let fetch_limit = limit.saturating_add(1);

        let mut sql = String::from(
            "SELECT event_id, ts_unix, hostname, vendor, facility, severity, event_code, \
             raw_message, normalized_message, template, template_fingerprint \
             FROM syslog_events \
             WHERE lowerUTF8(hostname) = lowerUTF8(?) \
             AND ts_unix >= ? AND ts_unix <= ?",
        );
        if request.severity.is_some() {
            sql.push_str(" AND severity = ?");
        }
        let text = request
            .text
            .as_deref()
            .map(str::trim)
            .filter(|v| !v.is_empty());
        if text.is_some_and(|value| value.len() > 512) {
            bail!("text filter is too long");
        }
        if text.is_some() {
            sql.push_str(
                " AND (positionCaseInsensitiveUTF8(raw_message, ?) > 0 \
                 OR positionCaseInsensitiveUTF8(normalized_message, ?) > 0)",
            );
        }
        sql.push_str(" ORDER BY ts_unix DESC LIMIT ?");

        let mut query = self
            .client
            .query(&sql)
            .with_option("max_execution_time", self.timeout_secs.to_string())
            .bind(&hostname)
            .bind(start)
            .bind(end);
        if let Some(severity) = request.severity {
            query = query.bind(severity);
        }
        if let Some(text) = text {
            query = query.bind(text).bind(text);
        }
        let mut events = query
            .bind(fetch_limit)
            .fetch_all::<SyslogEventRow>()
            .await?;
        let truncated = events.len() > limit as usize;
        events.truncate(limit as usize);

        Ok(DeviceEventsResponse {
            hostname,
            start_time_unix: start,
            end_time_unix: end,
            as_of_unix: as_of,
            count: events.len(),
            truncated,
            events,
        })
    }

    pub async fn severity_summary(
        &self,
        request: DeviceWindowRequest,
    ) -> Result<SeveritySummaryResponse> {
        let hostname = validate_hostname(&request.hostname)?;
        let (start, end, as_of) =
            self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        let severities = self
            .client
            .query(
                "SELECT severity, count() AS count FROM syslog_events \
                 WHERE lowerUTF8(hostname) = lowerUTF8(?) \
                 AND ts_unix >= ? AND ts_unix <= ? \
                 GROUP BY severity ORDER BY severity ASC",
            )
            .with_option("max_execution_time", self.timeout_secs.to_string())
            .bind(&hostname)
            .bind(start)
            .bind(end)
            .fetch_all::<SeverityCount>()
            .await?;
        let total = severities.iter().map(|item| item.count).sum();
        Ok(SeveritySummaryResponse {
            hostname,
            start_time_unix: start,
            end_time_unix: end,
            as_of_unix: as_of,
            total,
            severities,
        })
    }

    pub async fn device_patterns(
        &self,
        request: DevicePatternsRequest,
    ) -> Result<DevicePatternsResponse> {
        let hostname = validate_hostname(&request.hostname)?;
        let (start, end, as_of) =
            self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        let limit = request.limit.unwrap_or(20).clamp(1, self.max_results);
        let fetch_limit = limit.saturating_add(1);
        let mut patterns = self
            .client
            .query(
                "SELECT template, count() AS count, max(ts_unix) AS last_seen_unix \
                 FROM syslog_events \
                 WHERE lowerUTF8(hostname) = lowerUTF8(?) \
                 AND ts_unix >= ? AND ts_unix <= ? AND template != '' \
                 GROUP BY template ORDER BY count DESC, last_seen_unix DESC LIMIT ?",
            )
            .with_option("max_execution_time", self.timeout_secs.to_string())
            .bind(&hostname)
            .bind(start)
            .bind(end)
            .bind(fetch_limit)
            .fetch_all::<LogPattern>()
            .await?;
        let truncated = patterns.len() > limit as usize;
        patterns.truncate(limit as usize);
        Ok(DevicePatternsResponse {
            hostname,
            start_time_unix: start,
            end_time_unix: end,
            as_of_unix: as_of,
            count: patterns.len(),
            truncated,
            patterns,
        })
    }

    fn resolve_window(&self, start: Option<i64>, end: Option<i64>) -> Result<(i64, i64, i64)> {
        resolve_window(
            start,
            end,
            unix_now(),
            self.default_window_secs,
            self.max_window_secs,
        )
    }
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

fn validate_hostname(hostname: &str) -> Result<String> {
    let hostname = hostname.trim();
    if hostname.is_empty() {
        bail!("hostname is required");
    }
    if hostname.len() > 255 {
        bail!("hostname is too long");
    }
    Ok(hostname.to_string())
}

fn resolve_window(
    start: Option<i64>,
    end: Option<i64>,
    now: i64,
    default_window_secs: u64,
    max_window_secs: u64,
) -> Result<(i64, i64, i64)> {
    let end = end.unwrap_or(now);
    let default_window = i64::try_from(default_window_secs).unwrap_or(i64::MAX);
    let start = start.unwrap_or_else(|| end.saturating_sub(default_window));
    if start > end {
        bail!("start_time_unix must not be after end_time_unix");
    }
    let max_window = i64::try_from(max_window_secs).unwrap_or(i64::MAX);
    if end.saturating_sub(start) > max_window {
        bail!("requested time window exceeds the configured maximum");
    }
    Ok((start, end, now))
}

#[cfg(test)]
mod tests {
    use super::{DeviceEventsRequest, LogQueryService, resolve_window, validate_hostname};
    use crate::storage::clickhouse::SyslogEventRow;
    use clickhouse::{Client, test};

    #[test]
    fn window_defaults_to_bounded_period_ending_now() {
        assert_eq!(
            resolve_window(None, None, 10_000, 3_600, 86_400).unwrap(),
            (6_400, 10_000, 10_000)
        );
    }

    #[test]
    fn window_rejects_reverse_and_oversized_ranges() {
        assert!(resolve_window(Some(20), Some(10), 30, 10, 100).is_err());
        assert!(resolve_window(Some(0), Some(101), 101, 10, 100).is_err());
    }

    #[test]
    fn hostname_is_trimmed_and_required() {
        assert_eq!(validate_hostname(" edge-01 ").unwrap(), "edge-01");
        assert!(validate_hostname("  ").is_err());
    }

    #[tokio::test]
    async fn device_events_decodes_rows_and_reports_service_truncation() {
        let mock = test::Mock::new();
        let client = Client::default().with_url(mock.url());
        let row = |event_id: &str, timestamp: i64| SyslogEventRow {
            event_id: event_id.to_string(),
            ts_unix: timestamp,
            hostname: "edge-01".to_string(),
            vendor: "cisco".to_string(),
            facility: "LINK".to_string(),
            severity: 3,
            event_code: "UPDOWN".to_string(),
            raw_message: "interface changed state to down".to_string(),
            normalized_message: "interface changed state to down".to_string(),
            template: "interface changed state to down".to_string(),
            template_fingerprint: 42,
        };
        mock.add(test::handlers::provide(vec![
            row("event-2", 200),
            row("event-1", 100),
        ]));
        let service = LogQueryService {
            client,
            default_window_secs: 3_600,
            max_window_secs: 86_400,
            max_results: 200,
            timeout_secs: 8,
        };

        let response = service
            .device_events(DeviceEventsRequest {
                hostname: " edge-01 ".to_string(),
                start_time_unix: Some(0),
                end_time_unix: Some(300),
                severity: Some(3),
                text: Some("down".to_string()),
                limit: Some(1),
            })
            .await
            .unwrap();

        assert_eq!(response.hostname, "edge-01");
        assert_eq!(response.count, 1);
        assert!(response.truncated);
        assert_eq!(response.events[0].event_id, "event-2");
    }
}
