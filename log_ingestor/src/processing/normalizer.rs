use once_cell::sync::Lazy;
use regex::Regex;

static UUID_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")
        .unwrap()
});

static MAC_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}\b").unwrap()
});

static IPV4_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(\d{1,3}\.){3}\d{1,3}\b").unwrap()
});

static IPV6_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b([0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b").unwrap()
});

static HEX_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b0x[0-9a-fA-F]+\b").unwrap()
});

static NUMBER_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b\d+\b").unwrap()
});

pub fn normalize_message(input: &str) -> String {
    let mut out = input.to_owned();

    out = UUID_RE.replace_all(&out, "<UUID>").into_owned();
    out = MAC_RE.replace_all(&out, "<MAC>").into_owned();
    out = IPV6_RE.replace_all(&out, "<IP6>").into_owned();
    out = IPV4_RE.replace_all(&out, "<IP>").into_owned();
    out = HEX_RE.replace_all(&out, "<HEX>").into_owned();
    out = NUMBER_RE.replace_all(&out, "<NUM>").into_owned();

    collapse_whitespace(&out)
}

fn collapse_whitespace(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}
