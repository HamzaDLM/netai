use once_cell::sync::Lazy;
use regex::Regex;

use crate::types::IncomingSyslog;

static CISCO_PREFIX_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^%([A-Z0-9_]+)-([0-7])-([A-Z0-9_]+|\d+):\s*(.*)$")
        .expect("valid cisco prefix regex")
});

#[derive(Debug, Clone)]
pub struct ParsedSyslog {
    pub vendor: String,
    pub message: String,
    pub facility: Option<String>,
    pub severity: Option<u8>,
    pub event_code: Option<String>,
}

pub fn parse_syslog(log: &IncomingSyslog) -> ParsedSyslog {
    let vendor = detect_vendor(log);

    if let Some(caps) = CISCO_PREFIX_RE.captures(&log.syslog_message) {
        let facility = caps.get(1).map(|m| m.as_str().to_string());
        let severity = caps.get(2).and_then(|m| m.as_str().parse::<u8>().ok());
        let event_code = caps.get(3).map(|m| m.as_str().to_string());
        let message = caps
            .get(4)
            .map(|m| m.as_str().to_string())
            .unwrap_or_else(|| log.syslog_message.clone());

        return ParsedSyslog {
            vendor,
            message,
            facility,
            severity,
            event_code,
        };
    }

    ParsedSyslog {
        vendor,
        message: log.syslog_message.clone(),
        facility: None,
        severity: None,
        event_code: None,
    }
}

fn detect_vendor(log: &IncomingSyslog) -> String {
    if let Some(vendor) = log.vendor.as_deref() {
        let normalized = normalize_vendor_label(vendor);
        if normalized != "unknown" {
            return normalized;
        }
    }

    let message = log.syslog_message.to_lowercase();
    let hostname = log.syslog_hostname.to_lowercase();

    if message.contains("devname=")
        || message.contains("devid=")
        || message.contains("logid=")
        || message.contains("type=\"traffic\"")
    {
        return "fortinet".to_string();
    }

    if message.contains(",threat,")
        || message.contains(",traffic,")
        || message.contains("panos")
        || message.contains("palo alto")
    {
        return "palo_alto".to_string();
    }

    if message.contains("rt_flow")
        || message.contains("chassisd")
        || message.contains("rpd[")
        || hostname.contains("juniper")
    {
        return "juniper".to_string();
    }

    if message.contains("%asa-")
        || message.contains("%bgp-")
        || message.contains("%ospf-")
        || message.contains("%lineproto-")
        || hostname.starts_with("fw-")
        || hostname.starts_with("router-")
        || hostname.starts_with("sw-")
    {
        return "cisco".to_string();
    }

    if message.contains("big-ip")
        || message.contains("bigip")
        || message.contains("tmm[")
        || hostname.starts_with("f5-")
        || hostname.contains("bigip")
    {
        return "f5".to_string();
    }

    if hostname.contains("arista") || message.contains("eos") {
        return "arista".to_string();
    }

    if hostname.contains("aruba") || message.contains("aruba") {
        return "aruba".to_string();
    }

    "unknown".to_string()
}

fn normalize_vendor_label(value: &str) -> String {
    let cleaned = value.trim().to_lowercase().replace([' ', '-'], "_");
    match cleaned.as_str() {
        "pan" | "paloalto" | "pa" => "palo_alto".to_string(),
        "fortigate" | "fortios" => "fortinet".to_string(),
        "cisco_ios" | "cisco_nxos" | "cisco_xr" => "cisco".to_string(),
        "f5_bigip" | "bigip" => "f5".to_string(),
        "hp_aruba" => "aruba".to_string(),
        "" => "unknown".to_string(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn incoming(message: &str, hostname: &str, vendor: Option<&str>) -> IncomingSyslog {
        IncomingSyslog {
            syslog_timestamp: 1_700_000_000,
            syslog_hostname: hostname.to_string(),
            syslog_message: message.to_string(),
            vendor: vendor.map(str::to_string),
        }
    }

    #[test]
    fn parses_cisco_prefix_and_vendor_alias() {
        let log = incoming(
            "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down",
            "router-core-1",
            Some("cisco-ios"),
        );

        let parsed = parse_syslog(&log);

        assert_eq!(parsed.vendor, "cisco");
        assert_eq!(parsed.facility.as_deref(), Some("LINK"));
        assert_eq!(parsed.severity, Some(3));
        assert_eq!(parsed.event_code.as_deref(), Some("UPDOWN"));
        assert_eq!(
            parsed.message,
            "Interface GigabitEthernet1/0/1, changed state to down"
        );
    }

    #[test]
    fn detects_fortinet_from_kv_message() {
        let log = incoming(
            r#"date=2026-04-12 time=10:15:30 devname="FGT01" type="traffic" srcip=10.0.0.10"#,
            "edge-fw-1",
            None,
        );

        let parsed = parse_syslog(&log);
        assert_eq!(parsed.vendor, "fortinet");
    }

    #[test]
    fn detects_arista_from_hostname() {
        let log = incoming("Port-Channel1 is up", "arista-leaf-01", None);
        let parsed = parse_syslog(&log);
        assert_eq!(parsed.vendor, "arista");
    }

    #[test]
    fn detects_juniper_from_message() {
        let log = incoming(
            "RT_FLOW_SESSION_CREATE: session created 10.0.0.1/2222->8.8.8.8/53",
            "branch-srx-1",
            None,
        );
        let parsed = parse_syslog(&log);
        assert_eq!(parsed.vendor, "juniper");
    }

    #[test]
    fn detects_f5_from_bigip_indicators() {
        let log = incoming(
            "tmm[12345]: 01260013:5: Pool /Common/web members available",
            "f5-ltm-1",
            None,
        );
        let parsed = parse_syslog(&log);
        assert_eq!(parsed.vendor, "f5");
    }
}
