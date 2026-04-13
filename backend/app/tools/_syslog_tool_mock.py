from typing import Any

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
