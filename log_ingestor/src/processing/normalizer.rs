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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::processing::parser::ParsedSyslog;

    fn parsed(vendor: &str, message: &str) -> ParsedSyslog {
        ParsedSyslog {
            vendor: vendor.to_string(),
            message: message.to_string(),
            facility: None,
            severity: None,
            event_code: None,
        }
    }

    #[test]
    fn normalizes_cisco_like_message() {
        let input = parsed(
            "cisco",
            "%BGP-5-ADJCHANGE: neighbor 10.10.10.10 on GigabitEthernet1/0/1 changed state",
        );
        let output = normalize_message(&input);

        assert!(output.contains("%BGP-<NUM>-ADJCHANGE"));
        assert!(output.contains("<IFACE>"));
        assert!(output.contains("<IP>"));
    }

    #[test]
    fn normalizes_fortinet_kv_fields() {
        let input = parsed(
            "fortinet",
            r#"srcip=10.0.0.1 dstip=8.8.8.8 srcport=54321 policyid=77 eventtime=1712345678"#,
        );
        let output = normalize_message(&input);

        assert!(output.contains("srcip=<IP>"));
        assert!(output.contains("dstip=<IP>"));
        assert!(output.contains("srcport=<PORT>"));
        assert!(output.contains("policyid=<ID>"));
        assert!(output.contains("eventtime=<TIME>"));
    }

    #[test]
    fn normalizes_juniper_event_marker() {
        let input = parsed(
            "juniper",
            "RT_FLOW: session close from ge-0/0/0.0 to 192.0.2.10",
        );
        let output = normalize_message(&input);

        assert!(output.contains("<JUNOS_EVENT>"));
        assert!(output.contains("<IP>"));
    }

    #[test]
    fn normalizes_palo_alto_csv_spacing() {
        let input = parsed("palo_alto", "x,  y , z ");
        let output = normalize_message(&input);
        assert_eq!(output, "x,y,z");
    }

    #[test]
    fn normalizes_f5_with_generic_placeholders() {
        let input = parsed(
            "f5",
            "tmm[12345]: Connection from 10.20.30.40:443 to 172.16.0.11:8080",
        );
        let output = normalize_message(&input);

        assert!(output.contains("<IP>"));
        assert!(output.contains("<NUM>"));
    }
}
