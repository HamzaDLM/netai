use once_cell::sync::Lazy;
use regex::Regex;

use super::parser::ParsedSyslog;

static UUID_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")
        .unwrap()
});

static MAC_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}\b").unwrap());

static IPV4_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\b(\d{1,3}\.){3}\d{1,3}\b").unwrap());

static IPV6_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b([0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b").unwrap());

static HEX_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\b0x[0-9a-fA-F]+\b").unwrap());

static NUMBER_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\b\d+\b").unwrap());

static KV_PAIR_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"(?P<key>\b[a-zA-Z_][a-zA-Z0-9_-]*)=(?P<value>"[^"]*"|\S+)"#).unwrap()
});

static CISCO_SEVERITY_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?P<prefix>%[A-Z0-9_]+)-[0-7]-(?P<code>[A-Z0-9_]+|\d+)").unwrap());

static IFACE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b([a-z]{1,4}-\d+/\d+/\d+(\.\d+)?|[A-Z][A-Za-z-]*\d+(/[0-9]+){0,2})\b").unwrap()
});

pub fn normalize_message(parsed: &ParsedSyslog) -> String {
    let mut out = parsed.message.clone();

    out = UUID_RE.replace_all(&out, "<UUID>").into_owned();
    out = MAC_RE.replace_all(&out, "<MAC>").into_owned();
    out = IPV6_RE.replace_all(&out, "<IP6>").into_owned();
    out = IPV4_RE.replace_all(&out, "<IP>").into_owned();
    out = HEX_RE.replace_all(&out, "<HEX>").into_owned();
    out = NUMBER_RE.replace_all(&out, "<NUM>").into_owned();

    out = match parsed.vendor.as_str() {
        "fortinet" => normalize_fortinet_kv(&out),
        "cisco" | "arista" | "aruba" => normalize_cisco_like(&out),
        "juniper" => normalize_juniper(&out),
        "palo_alto" => normalize_palo_alto(&out),
        _ => out,
    };

    collapse_whitespace(&out)
}

fn collapse_whitespace(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn normalize_fortinet_kv(input: &str) -> String {
    KV_PAIR_RE
        .replace_all(input, |caps: &regex::Captures<'_>| {
            let key = caps
                .name("key")
                .map(|m| m.as_str().to_lowercase())
                .unwrap_or_default();
            let placeholder = if key.contains("ip") {
                "<IP>"
            } else if key.contains("port") {
                "<PORT>"
            } else if key.contains("time") || key.contains("date") {
                "<TIME>"
            } else if key.contains("id") || key.contains("session") {
                "<ID>"
            } else {
                "<VAL>"
            };
            format!("{}={}", &caps["key"], placeholder)
        })
        .into_owned()
}

fn normalize_cisco_like(input: &str) -> String {
    let with_severity = CISCO_SEVERITY_RE
        .replace_all(input, "${prefix}-<SEV>-${code}")
        .into_owned();
    IFACE_RE.replace_all(&with_severity, "<IFACE>").into_owned()
}

fn normalize_juniper(input: &str) -> String {
    let with_event = input.replace("RT_FLOW", "<JUNOS_EVENT>");
    IFACE_RE.replace_all(&with_event, "<IFACE>").into_owned()
}

fn normalize_palo_alto(input: &str) -> String {
    input
        .split(',')
        .map(|part| part.trim())
        .collect::<Vec<_>>()
        .join(",")
}
