import re
from dataclasses import dataclass


IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)


@dataclass(slots=True)
class ParsedQuery:
    ips: list[str]
    hostnames: list[str]


def parse_query_filters(question: str) -> ParsedQuery:
    ips = sorted(set(IPV4_RE.findall(question)))

    hostnames: list[str] = []
    for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]{2,}\b", question):
        low = token.lower()
        if any(
            prefix in low for prefix in ["router", "switch", "sw-", "fw-", "vpn", "wlc"]
        ):
            hostnames.append(token)

    return ParsedQuery(ips=ips, hostnames=sorted(set(hostnames)))
