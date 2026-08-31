use anyhow::{Result, bail};
use clickhouse::{Client, Row};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{config::Config, storage::clickhouse::build_client};

pub const DEFAULT_RESULT_LIMIT: u32 = 20;

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
    #[schemars(description = "Optional case-insensitive text in the original message.")]
    pub text: Option<String>,
    #[schemars(description = "Maximum events to return; defaults to 20 and has a hard cap.")]
    pub limit: Option<u32>,
}

#[derive(Clone, Debug, Deserialize, Row, Serialize)]
struct DeviceEventQueryRow {
    ts_unix: i64,
    vendor: String,
    facility: String,
    severity: i16,
    event_code: String,
    message: String,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct LogEvent {
    pub ts_unix: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub severity: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub facility: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_code: Option<String>,
    pub message: String,
}

impl From<DeviceEventQueryRow> for LogEvent {
    fn from(row: DeviceEventQueryRow) -> Self {
        Self {
            ts_unix: row.ts_unix,
            severity: known_severity(row.severity),
            facility: non_empty(row.facility),
            event_code: non_empty(row.event_code),
            message: row.message,
        }
    }
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct DeviceEventsResponse {
    pub hostname: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vendor: Option<String>,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub count: usize,
    pub truncated: bool,
    pub events: Vec<LogEvent>,
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

#[derive(Clone, Debug, Deserialize, Row, Serialize)]
struct SeverityCountRow {
    severity: i16,
    count: u64,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct SeverityCount {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub severity: Option<u8>,
    pub count: u64,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct SeveritySummaryResponse {
    pub hostname: String,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub total: u64,
    pub severities: Vec<SeverityCount>,
}

#[derive(Clone, Debug, Deserialize, JsonSchema)]
pub struct EventSummaryRequest {
    #[schemars(description = "Device hostname, matched case-insensitively.")]
    pub hostname: String,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to one hour ago.")]
    pub start_time_unix: Option<i64>,
    #[schemars(description = "Inclusive UTC Unix timestamp. Defaults to now.")]
    pub end_time_unix: Option<i64>,
    #[schemars(description = "Maximum groups to return; defaults to 20 and has a hard cap.")]
    pub limit: Option<u32>,
}

#[derive(Clone, Debug, Deserialize, Row, Serialize)]
struct EventSummaryQueryRow {
    severity: i16,
    facility: String,
    event_code: String,
    count: u64,
    last_seen_unix: i64,
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct EventSummaryGroup {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub severity: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub facility: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_code: Option<String>,
    pub count: u64,
    pub last_seen_unix: i64,
}

impl From<EventSummaryQueryRow> for EventSummaryGroup {
    fn from(row: EventSummaryQueryRow) -> Self {
        Self {
            severity: known_severity(row.severity),
            facility: non_empty(row.facility),
            event_code: non_empty(row.event_code),
            count: row.count,
            last_seen_unix: row.last_seen_unix,
        }
    }
}

#[derive(Clone, Debug, Serialize, JsonSchema)]
pub struct EventSummaryResponse {
    pub hostname: String,
    pub start_time_unix: i64,
    pub end_time_unix: i64,
    pub count: usize,
    pub truncated: bool,
    pub groups: Vec<EventSummaryGroup>,
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
        let (start, end) = self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        if let Some(severity) = request.severity
            && !(-1..=7).contains(&severity)
        {
            bail!("severity must be between -1 and 7");
        }
        let limit = request
            .limit
            .unwrap_or(DEFAULT_RESULT_LIMIT)
            .clamp(1, self.max_results);
        let fetch_limit = limit.saturating_add(1);

        let mut sql = String::from(
            "SELECT ts_unix, vendor, facility, severity, event_code, raw_message AS message \
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
            .filter(|value| !value.is_empty());
        if text.is_some_and(|value| value.len() > 512) {
            bail!("text filter is too long");
        }
        if text.is_some() {
            sql.push_str(" AND positionCaseInsensitiveUTF8(raw_message, ?) > 0");
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
            query = query.bind(text);
        }
        let mut rows = query
            .bind(fetch_limit)
            .fetch_all::<DeviceEventQueryRow>()
            .await?;
        let truncated = rows.len() > limit as usize;
        rows.truncate(limit as usize);
        let vendor = rows.iter().find_map(|row| known_vendor(row.vendor.clone()));
        let events = rows.into_iter().map(LogEvent::from).collect::<Vec<_>>();

        Ok(DeviceEventsResponse {
            hostname,
            vendor,
            start_time_unix: start,
            end_time_unix: end,
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
        let (start, end) = self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        let rows = self
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
            .fetch_all::<SeverityCountRow>()
            .await?;
        let total = rows.iter().map(|item| item.count).sum();
        let severities = rows
            .into_iter()
            .map(|row| SeverityCount {
                severity: known_severity(row.severity),
                count: row.count,
            })
            .collect();
        Ok(SeveritySummaryResponse {
            hostname,
            start_time_unix: start,
            end_time_unix: end,
            total,
            severities,
        })
    }

    pub async fn event_summary(
        &self,
        request: EventSummaryRequest,
    ) -> Result<EventSummaryResponse> {
        let hostname = validate_hostname(&request.hostname)?;
        let (start, end) = self.resolve_window(request.start_time_unix, request.end_time_unix)?;
        let limit = request
            .limit
            .unwrap_or(DEFAULT_RESULT_LIMIT)
            .clamp(1, self.max_results);
        let fetch_limit = limit.saturating_add(1);
        let mut rows = self
            .client
            .query(
                "SELECT severity, facility, event_code, count() AS count, \
                 max(ts_unix) AS last_seen_unix \
                 FROM syslog_events \
                 WHERE lowerUTF8(hostname) = lowerUTF8(?) \
                 AND ts_unix >= ? AND ts_unix <= ? \
                 AND (severity != -1 OR facility != '' OR event_code != '') \
                 GROUP BY severity, facility, event_code \
                 ORDER BY count DESC, last_seen_unix DESC LIMIT ?",
            )
            .with_option("max_execution_time", self.timeout_secs.to_string())
            .bind(&hostname)
            .bind(start)
            .bind(end)
            .bind(fetch_limit)
            .fetch_all::<EventSummaryQueryRow>()
            .await?;
        let truncated = rows.len() > limit as usize;
        rows.truncate(limit as usize);
        let groups = rows
            .into_iter()
            .map(EventSummaryGroup::from)
            .collect::<Vec<_>>();
        Ok(EventSummaryResponse {
            hostname,
            start_time_unix: start,
            end_time_unix: end,
            count: groups.len(),
            truncated,
            groups,
        })
    }

    fn resolve_window(&self, start: Option<i64>, end: Option<i64>) -> Result<(i64, i64)> {
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
) -> Result<(i64, i64)> {
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
    Ok((start, end))
}

fn known_severity(value: i16) -> Option<u8> {
    u8::try_from(value).ok().filter(|severity| *severity <= 7)
}

fn non_empty(value: String) -> Option<String> {
    let value = value.trim().to_string();
    (!value.is_empty()).then_some(value)
}

fn known_vendor(value: String) -> Option<String> {
    non_empty(value).filter(|vendor| !vendor.eq_ignore_ascii_case("unknown"))
}

#[cfg(test)]
mod tests {
    use super::{
        DeviceEventQueryRow, DeviceEventsRequest, EventSummaryGroup, EventSummaryQueryRow,
        EventSummaryRequest, LogEvent, LogQueryService, non_empty, resolve_window,
        validate_hostname,
    };
    use clickhouse::{Client, test};

    #[test]
    fn window_defaults_to_bounded_period_ending_now() {
        assert_eq!(
            resolve_window(None, None, 10_000, 3_600, 86_400).unwrap(),
            (6_400, 10_000)
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

    #[test]
    fn unknown_or_blank_metadata_is_omitted_from_mcp_json() {
        let event = LogEvent {
            ts_unix: 100,
            severity: None,
            facility: non_empty(String::new()),
            event_code: non_empty(String::new()),
            message: "unparsed event".to_string(),
        };

        let value = serde_json::to_value(event).unwrap();
        assert_eq!(
            value,
            serde_json::json!({"ts_unix": 100, "message": "unparsed event"})
        );
    }

    #[test]
    fn structured_summary_maps_storage_sentinels_to_optional_fields() {
        let group = EventSummaryGroup::from(EventSummaryQueryRow {
            severity: -1,
            facility: "LINK".to_string(),
            event_code: String::new(),
            count: 12,
            last_seen_unix: 200,
        });

        let value = serde_json::to_value(group).unwrap();
        assert_eq!(
            value,
            serde_json::json!({
                "facility": "LINK",
                "count": 12,
                "last_seen_unix": 200
            })
        );
    }

    #[tokio::test]
    async fn device_events_returns_a_minimal_payload_and_reports_truncation() {
        let mock = test::Mock::new();
        let client = Client::default().with_url(mock.url());
        let row = |timestamp: i64| DeviceEventQueryRow {
            ts_unix: timestamp,
            vendor: "cisco".to_string(),
            facility: "LINK".to_string(),
            severity: 3,
            event_code: "UPDOWN".to_string(),
            message: "interface changed state to down".to_string(),
        };
        mock.add(test::handlers::provide(vec![row(200), row(100)]));
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
        assert_eq!(response.vendor.as_deref(), Some("cisco"));
        assert_eq!(response.count, 1);
        assert!(response.truncated);
        assert_eq!(
            response.events[0].message,
            "interface changed state to down"
        );
    }

    #[tokio::test]
    async fn event_summary_returns_structured_groups_and_reports_truncation() {
        let mock = test::Mock::new();
        let client = Client::default().with_url(mock.url());
        let row = |event_code: &str, count: u64| EventSummaryQueryRow {
            severity: 3,
            facility: "LINK".to_string(),
            event_code: event_code.to_string(),
            count,
            last_seen_unix: 200,
        };
        mock.add(test::handlers::provide(vec![
            row("UPDOWN", 12),
            row("CHANGED", 4),
        ]));
        let service = LogQueryService {
            client,
            default_window_secs: 3_600,
            max_window_secs: 86_400,
            max_results: 200,
            timeout_secs: 8,
        };

        let response = service
            .event_summary(EventSummaryRequest {
                hostname: "edge-01".to_string(),
                start_time_unix: Some(0),
                end_time_unix: Some(300),
                limit: Some(1),
            })
            .await
            .unwrap();

        assert_eq!(response.count, 1);
        assert!(response.truncated);
        assert_eq!(response.groups[0].event_code.as_deref(), Some("UPDOWN"));
        assert_eq!(response.groups[0].count, 12);
    }
}
