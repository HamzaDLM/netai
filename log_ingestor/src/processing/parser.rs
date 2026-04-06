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
        "hp_aruba" => "aruba".to_string(),
        "" => "unknown".to_string(),
        other => other.to_string(),
    }
}
