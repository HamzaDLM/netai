from typing import Annotated, Any

from haystack.tools import tool

_FAKE_EVIDENCE: list[dict[str, Any]] = [
    {
        "type": "event",
        "ref": "evt-1001",
        "content": "BGP session to ISP-B flapped 4 times on dist-rtr-nyc-01 in the last 10 minutes.",
        "score": 0.94,
        "timestamp": "2026-04-13T09:41:00Z",
    },
    {
        "type": "event",
        "ref": "evt-1002",
        "content": "Interface xe-0/0/2 on dist-rtr-nyc-01 transitioned to down/down.",
        "score": 0.89,
        "timestamp": "2026-04-13T09:39:00Z",
    },
    {
        "type": "template",
        "ref": "tpl-bgp-flap-01",
        "content": "Pattern matches recurring BGP instability with intermittent packet loss.",
        "score": 0.81,
        "timestamp": "2026-04-10T00:00:00Z",
    },
]

_FAKE_LOG_ROWS: list[dict[str, Any]] = [
    {
        "event_id": "evt-1001",
        "ts_unix": 1776073260,
        "hostname": "dist-rtr-nyc-01",
        "vendor": "cisco",
        "facility": "LINK",
        "severity": 3,
        "event_code": "UPDOWN",
        "raw_message": "Interface xe-0/0/2 changed state to down",
        "normalized_message": "Interface <IFACE> changed state to down",
        "template": "Interface <IFACE> changed state to down",
    },
    {
        "event_id": "evt-1002",
        "ts_unix": 1776073200,
        "hostname": "dist-rtr-nyc-01",
        "vendor": "cisco",
        "facility": "BGP",
        "severity": 4,
        "event_code": "ADJCHANGE",
        "raw_message": "BGP neighbor 10.1.1.1 down",
        "normalized_message": "BGP neighbor <IP> down",
        "template": "BGP neighbor <IP> down",
    },
    {
        "event_id": "evt-1003",
        "ts_unix": 1776073140,
        "hostname": "edge-fw-par-01",
        "vendor": "fortinet",
        "facility": "SYSTEM",
        "severity": 5,
        "event_code": "AUTH",
        "raw_message": "Admin login successful from 10.10.10.7",
        "normalized_message": "Admin login successful from <IP>",
        "template": "Admin login successful from <IP>",
    },
]


@tool(name="syslog.get_evidence")  # type: ignore[operator]
def get_syslog_evidence(question: str, top_k: int = 8) -> dict[str, Any]:
    """Return fake ranked syslog evidence for offline/dev usage."""
    safe_top_k = max(1, min(int(top_k), 50))
    query = (question or "").strip().lower()
    if query:
        filtered = [
            row for row in _FAKE_EVIDENCE if query.split()[0] in row["content"].lower()
        ]
        rows = filtered if filtered else _FAKE_EVIDENCE
    else:
        rows = _FAKE_EVIDENCE

    evidence = rows[:safe_top_k]
    return {
        "question": question,
        "top_k": safe_top_k,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "filters": {},
    }


@tool(name="syslog.get_logs")  # type: ignore[operator]
def get_syslog_logs(
    hostname: Annotated[str, "Hostname filter for syslog events (partial match)."],
    severity: Annotated[int | None, "Optional severity filter (-1 to 7)."] = None,
) -> dict[str, Any]:
    """Return latest 40 fake syslog events by hostname, optionally filtered by severity."""
    hostname_value = (hostname or "").strip()
    if not hostname_value:
        return {
            "hostname": "",
            "severity": severity,
            "limit": 40,
            "count": 0,
            "logs": [],
            "error": "hostname_required",
        }

    if severity is not None and (int(severity) < -1 or int(severity) > 7):
        return {
            "hostname": hostname_value,
            "severity": severity,
            "limit": 40,
            "count": 0,
            "logs": [],
            "error": "severity_out_of_range:-1_to_7",
        }

    hostname_filter = hostname_value.lower()
    rows = [
        row
        for row in _FAKE_LOG_ROWS
        if hostname_filter in str(row.get("hostname", "")).lower()
    ]
    if severity is not None:
        rows = [row for row in rows if int(row.get("severity", -1)) == int(severity)]

    logs = rows[:40]
    return {
        "hostname": hostname_value,
        "severity": severity,
        "limit": 40,
        "count": len(logs),
        "logs": logs,
    }
