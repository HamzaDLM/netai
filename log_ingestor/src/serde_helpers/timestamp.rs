use chrono::DateTime;
use serde::de::{self, Deserializer, Visitor};
use std::fmt;

pub fn deserialize_unix_ts<'de, D>(deserializer: D) -> Result<i64, D::Error>
where
    D: Deserializer<'de>,
{
    struct TimestampVisitor;

    impl Visitor<'_> for TimestampVisitor {
        type Value = i64;

        fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
            formatter.write_str("unix timestamp (integer) or RFC3339 datetime string")
        }

        fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            Ok(value)
        }

        fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            i64::try_from(value).map_err(|_| E::custom("timestamp overflows i64"))
        }

        fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            parse_timestamp_str(value).map_err(E::custom)
        }

        fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            parse_timestamp_str(&value).map_err(E::custom)
        }
    }

    deserializer.deserialize_any(TimestampVisitor)
}

fn parse_timestamp_str(value: &str) -> Result<i64, String> {
    if let Ok(ts) = value.parse::<i64>() {
        return Ok(ts);
    }

    DateTime::parse_from_rfc3339(value)
        .map(|dt| dt.timestamp())
        .map_err(|_| format!("invalid timestamp string '{value}'"))
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    #[derive(Deserialize)]
    struct TimestampEnvelope {
        #[serde(deserialize_with = "super::deserialize_unix_ts")]
        ts: i64,
    }

    #[test]
    fn deserialize_timestamp_from_integer() {
        let input = r#"{"ts":1700000000}"#;
        let parsed: TimestampEnvelope = serde_json::from_str(input).expect("valid payload");
        assert_eq!(parsed.ts, 1700000000);
    }

    #[test]
    fn deserialize_timestamp_from_numeric_string() {
        let input = r#"{"ts":"1700000001"}"#;
        let parsed: TimestampEnvelope = serde_json::from_str(input).expect("valid payload");
        assert_eq!(parsed.ts, 1700000001);
    }

    #[test]
    fn deserialize_timestamp_from_rfc3339() {
        let input = r#"{"ts":"2026-04-10T12:34:56Z"}"#;
        let parsed: TimestampEnvelope = serde_json::from_str(input).expect("valid payload");
        assert_eq!(parsed.ts, 1_775_824_496);
    }
}
