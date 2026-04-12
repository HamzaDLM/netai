use log_ingestor::processing::dedup::TemplateDeduplicator;
use log_ingestor::processing::normalizer::normalize_message;
use log_ingestor::processing::parser::parse_syslog;
use log_ingestor::processing::template::build_template;
use log_ingestor::types::IncomingSyslog;

fn sample_log(hostname: &str, message: &str) -> IncomingSyslog {
    IncomingSyslog {
        syslog_timestamp: 1_712_345_678,
        syslog_hostname: hostname.to_string(),
        syslog_message: message.to_string(),
        vendor: None,
    }
}

#[test]
fn vendor_detection_examples_cover_target_vendors() {
    let cisco = sample_log(
        "router-edge-01",
        "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down",
    );
    let fortinet = sample_log(
        "sec-fw-01",
        r#"date=2026-04-12 time=10:00:01 devname="FGT-A" type="traffic" srcip=10.1.1.1 dstip=8.8.8.8"#,
    );
    let arista = sample_log(
        "arista-leaf-12",
        "EOS BGP adjacency change for peer 10.0.0.2",
    );
    let f5 = sample_log(
        "f5-ltm-02",
        "tmm[22990]: 01260013:5: Pool /Common/web members available",
    );
    let juniper = sample_log(
        "branch-srx-44",
        "RT_FLOW_SESSION_CREATE: session created 10.0.0.1/33333->1.1.1.1/53",
    );

    assert_eq!(parse_syslog(&cisco).vendor, "cisco");
    assert_eq!(parse_syslog(&fortinet).vendor, "fortinet");
    assert_eq!(parse_syslog(&arista).vendor, "arista");
    assert_eq!(parse_syslog(&f5).vendor, "f5");
    assert_eq!(parse_syslog(&juniper).vendor, "juniper");
}

#[test]
fn end_to_end_template_generation_and_dedup_for_vendor_samples() {
    let samples = vec![
        sample_log(
            "router-core-1",
            "%BGP-5-ADJCHANGE: neighbor 10.10.10.10 on GigabitEthernet1/0/1 changed state",
        ),
        sample_log(
            "sec-fw-01",
            r#"srcip=10.1.1.1 dstip=192.0.2.50 srcport=51000 policyid=77 eventtime=1712345678"#,
        ),
        sample_log(
            "arista-spine-03",
            "EOS interface Ethernet2 changed state to up",
        ),
        sample_log(
            "f5-ltm-02",
            "BIG-IP notice: connection from 10.20.30.40:443 to 172.16.0.11:8080",
        ),
        sample_log(
            "branch-juniper-01",
            "RT_FLOW: session close from ge-0/0/0.0 to 192.0.2.10",
        ),
    ];

    let dedup = TemplateDeduplicator::new();

    for log in &samples {
        let parsed = parse_syslog(log);
        let normalized = normalize_message(&parsed);
        let template = build_template(normalized.clone());
        let key = format!("{}::{}", parsed.vendor, template.template);

        assert!(!template.template.is_empty());
        assert!(dedup.is_new(&key));
        assert!(!dedup.is_new(&key));
    }

    assert_eq!(dedup.len(), samples.len());
}
