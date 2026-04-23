import json
import re
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from haystack.dataclasses import ChatMessage

from app.core.config import project_settings
from app.llm import llm
from app.prompts.log_qa import LOG_QA_PROMPT
from app.tools import netai_tool

IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
SYSLOG_HOST_LOG_LIMIT = 40


@dataclass(slots=True)
class ParsedSyslogQuery:
    ips: list[str]
    hostnames: list[str]


@dataclass(slots=True)
class SyslogEvidence:
    source: str
    content: str
    score: float


@dataclass(slots=True)
class SyslogQAResult:
    answer: str
    filters: dict[str, list[str]]
    evidence: list[dict[str, Any]]
    used_llm: bool


def _escape_sql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _extract_keywords(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_.:/-]{3,}", query.lower())
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "what",
        "when",
        "where",
        "show",
        "logs",
        "about",
        "into",
        "have",
        "been",
        "were",
        "this",
        "last",
        "why",
        "how",
    }
    uniq = []
    seen = set()
    for token in tokens:
        if token in stopwords:
            continue
        if token not in seen:
            seen.add(token)
            uniq.append(token)
    return uniq[:12]


def _normalize_severity(value: int | None) -> int | None:
    if value is None:
        return None
    severity_value = int(value)
    if severity_value < -1 or severity_value > 7:
        raise ValueError("severity_out_of_range:-1_to_7")
    return severity_value


def _parse_query_filters(question: str) -> ParsedSyslogQuery:
    ips = sorted(set(IPV4_RE.findall(question)))

    hostnames: list[str] = []
    for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]{2,}\b", question):
        low = token.lower()
        if any(
            prefix in low for prefix in ["router", "switch", "sw-", "fw-", "vpn", "wlc"]
        ):
            hostnames.append(token)

    return ParsedSyslogQuery(ips=ips, hostnames=sorted(set(hostnames)))


def _build_event_sql(
    *,
    database: str,
    top_k: int,
    lookback_seconds: int,
    ips: list[str],
    hostnames: list[str],
    keywords: list[str],
) -> str:
    where_clauses = [
        f"ts_unix >= toUnixTimestamp(now()) - {max(1, int(lookback_seconds))}",
    ]

    text_conditions: list[str] = []
    for ip in ips:
        ip_safe = _escape_sql(ip)
        text_conditions.append(f"position(raw_message, '{ip_safe}') > 0")

    for hn in hostnames:
        hn_safe = _escape_sql(hn.lower())
        text_conditions.append(
            f"positionCaseInsensitiveUTF8(hostname, '{hn_safe}') > 0 OR positionCaseInsensitiveUTF8(raw_message, '{hn_safe}') > 0"
        )

    for kw in keywords:
        kw_safe = _escape_sql(kw.lower())
        text_conditions.append(
            f"positionCaseInsensitiveUTF8(raw_message, '{kw_safe}') > 0 OR positionCaseInsensitiveUTF8(template, '{kw_safe}') > 0"
        )

    if text_conditions:
        where_clauses.append("(" + " OR ".join(text_conditions) + ")")

    top_k_sanitized = max(1, min(int(top_k), 200))
    where_sql = " AND ".join(where_clauses)
    return (
        "SELECT ts_unix, hostname, raw_message, template "
        f"FROM {database}.syslog_events "
        f"WHERE {where_sql} "
        "ORDER BY ts_unix DESC "
        f"LIMIT {top_k_sanitized} "
        "FORMAT JSON"
    )


def _build_host_logs_sql(
    *,
    database: str,
    hostname: str,
    severity: int | None,
) -> str:
    safe_hostname = _escape_sql(hostname.lower())
    where_clauses = [
        f"positionCaseInsensitiveUTF8(hostname, '{safe_hostname}') > 0",
    ]
    if severity is not None:
        where_clauses.append(f"severity = {severity}")
    where_sql = " AND ".join(where_clauses)
    return (
        "SELECT event_id, ts_unix, hostname, vendor, facility, severity, event_code, "
        "raw_message, normalized_message, template "
        f"FROM {database}.syslog_events "
        f"WHERE {where_sql} "
        "ORDER BY ts_unix DESC "
        f"LIMIT {SYSLOG_HOST_LOG_LIMIT} "
        "FORMAT JSON"
    )


class SyslogQAEngine:
    def __init__(self) -> None:
        self.clickhouse_base_url = project_settings.CLICKHOUSE_URL.rstrip("/")
        self.clickhouse_database = project_settings.CLICKHOUSE_DB
        self.clickhouse_user = project_settings.CLICKHOUSE_USER
        self.clickhouse_password = project_settings.CLICKHOUSE_PASSWORD
        self.qdrant_base_url = project_settings.QDRANT_URL.rstrip("/")
        self.qdrant_collection = project_settings.QDRANT_COLLECTION

    def retrieve_evidence(
        self, *, question: str, top_k: int | None = None
    ) -> dict[str, Any]:
        parsed = _parse_query_filters(question)
        effective_top_k = top_k or project_settings.LOG_QA_TOP_K
        event_top_k = max(effective_top_k, project_settings.LOG_QA_EVENT_TOP_K)

        event_hits = self._retrieve_event_hits(
            query=question,
            ips=parsed.ips,
            hostnames=parsed.hostnames,
            top_k=event_top_k,
        )
        template_hits = self._retrieve_template_hits(
            query=question, top_k=effective_top_k
        )

        combined_hits = [*event_hits, *template_hits]
        combined_hits.sort(key=lambda entry: entry.score, reverse=True)
        selected_hits = combined_hits[:effective_top_k]

        evidence = [
            {"source": e.source, "content": e.content, "score": e.score}
            for e in selected_hits
        ]

        return {
            "filters": {"ips": parsed.ips, "hostnames": parsed.hostnames},
            "evidence": evidence,
            "evidence_count": len(evidence),
        }

    def ask(self, *, question: str, top_k: int | None = None) -> SyslogQAResult:
        evidence_payload = self.retrieve_evidence(question=question, top_k=top_k)
        filters = evidence_payload["filters"]
        evidence = evidence_payload["evidence"]
        answer, used_llm = self._generate_answer(
            question=question, filters=filters, evidence=evidence
        )
        return SyslogQAResult(
            answer=answer,
            filters=filters,
            evidence=evidence,
            used_llm=used_llm,
        )

    def lookup_logs(
        self,
        *,
        hostname: str,
        severity: int | None = None,
    ) -> dict[str, Any]:
        hostname_value = (hostname or "").strip()
        if not hostname_value:
            return {
                "hostname": "",
                "severity": severity,
                "limit": SYSLOG_HOST_LOG_LIMIT,
                "count": 0,
                "logs": [],
                "error": "hostname_required",
            }

        try:
            severity_value = _normalize_severity(severity)
        except ValueError as exc:
            return {
                "hostname": hostname_value,
                "severity": severity,
                "limit": SYSLOG_HOST_LOG_LIMIT,
                "count": 0,
                "logs": [],
                "error": str(exc),
            }

        sql = _build_host_logs_sql(
            database=self.clickhouse_database,
            hostname=hostname_value,
            severity=severity_value,
        )

        try:
            with httpx.Client(
                timeout=8.0,
                auth=(self.clickhouse_user, self.clickhouse_password),
            ) as client:
                response = client.post(
                    f"{self.clickhouse_base_url}/",
                    params={"database": self.clickhouse_database},
                    content=sql.encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                )
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            return {
                "hostname": hostname_value,
                "severity": severity_value,
                "limit": SYSLOG_HOST_LOG_LIMIT,
                "count": 0,
                "logs": [],
                "error": f"clickhouse_query_failed:{exc}",
            }

        rows = body.get("data", [])
        logs = [
            {
                "event_id": row.get("event_id"),
                "ts_unix": row.get("ts_unix"),
                "hostname": row.get("hostname"),
                "vendor": row.get("vendor"),
                "facility": row.get("facility"),
                "severity": row.get("severity"),
                "event_code": row.get("event_code"),
                "raw_message": row.get("raw_message"),
                "normalized_message": row.get("normalized_message"),
                "template": row.get("template"),
            }
            for row in rows
        ]
        return {
            "hostname": hostname_value,
            "severity": severity_value,
            "limit": SYSLOG_HOST_LOG_LIMIT,
            "count": len(logs),
            "logs": logs,
        }

    def _retrieve_event_hits(
        self,
        *,
        query: str,
        ips: list[str],
        hostnames: list[str],
        top_k: int,
    ) -> list[SyslogEvidence]:
        keywords = _extract_keywords(query)
        sql = _build_event_sql(
            database=self.clickhouse_database,
            top_k=top_k,
            lookback_seconds=project_settings.LOG_QA_LOOKBACK_SECONDS,
            ips=ips,
            hostnames=hostnames,
            keywords=keywords,
        )

        try:
            with httpx.Client(
                timeout=8.0,
                auth=(self.clickhouse_user, self.clickhouse_password),
            ) as client:
                response = client.post(
                    f"{self.clickhouse_base_url}/",
                    params={"database": self.clickhouse_database},
                    content=sql.encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                )
                response.raise_for_status()
                body = response.json()
        except Exception:
            return []

        evidence: list[SyslogEvidence] = []
        for row in body.get("data", []):
            ts = row.get("ts_unix")
            hostname = row.get("hostname", "")
            raw_message = row.get("raw_message", "")
            template = row.get("template", "")

            score = 0.0
            lowered = raw_message.lower()
            for ip in ips:
                if ip in raw_message:
                    score += 3.0
            for hn in hostnames:
                if hn.lower() in hostname.lower() or hn.lower() in lowered:
                    score += 2.0
            for kw in keywords:
                if kw in lowered:
                    score += 0.5

            if score <= 0.0:
                score = 0.1

            content = (
                f'ts={ts} host={hostname} raw="{raw_message}" template="{template}"'
            )
            evidence.append(
                SyslogEvidence(source="clickhouse_event", content=content, score=score)
            )

        evidence.sort(key=lambda x: x.score, reverse=True)
        return evidence[:top_k]

    def _retrieve_template_hits(
        self, *, query: str, top_k: int
    ) -> list[SyslogEvidence]:
        url = (
            f"{self.qdrant_base_url}/collections/{self.qdrant_collection}/points/scroll"
        )
        payload = {
            "limit": 500,
            "with_payload": True,
            "with_vector": False,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                body = resp.json()
        except Exception:
            return []

        points = body.get("result", {}).get("points", [])
        tokens = {t for t in query.lower().split() if t}
        scored: list[SyslogEvidence] = []

        for point in points:
            template = point.get("payload", {}).get("template")
            if not isinstance(template, str) or not template:
                continue

            words = set(template.lower().split())
            overlap = len(tokens.intersection(words))
            score = float(overlap)
            if score > 0:
                scored.append(
                    SyslogEvidence(
                        source="qdrant_template",
                        content=template,
                        score=score,
                    )
                )

        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:top_k]

    def _generate_answer(
        self,
        *,
        question: str,
        filters: dict[str, list[str]],
        evidence: list[dict[str, Any]],
    ) -> tuple[str, bool]:
        if not evidence:
            return (
                "I could not find matching evidence in ClickHouse events or Qdrant templates for this query and lookback window.",
                False,
            )

        prompt = self._render_flat_prompt(
            question=question,
            filters=filters,
            evidence=evidence,
        )

        try:
            out = llm.run(messages=[ChatMessage.from_user(prompt)])
            replies = out.get("replies", [])
            if replies:
                first = replies[0]
                text = getattr(first, "text", None)
                return ((text if text else str(first)).strip(), True)
        except Exception as exc:
            return (f"Failed to generate syslog answer: {exc}", False)

        return ("No reply generated by the configured LLM generator.", False)

    def _render_flat_prompt(
        self,
        *,
        question: str,
        filters: dict[str, list[str]],
        evidence: list[dict[str, Any]],
    ) -> str:
        evidence_lines = "\n".join(
            [f"[{idx}] {ev['content']}" for idx, ev in enumerate(evidence, start=1)]
        )
        return (
            f"{LOG_QA_PROMPT}\n\n"
            f"Question:\n{question}\n\n"
            f"Parsed filters:\n{json.dumps(filters)}\n\n"
            f"Evidence:\n{evidence_lines}\n"
        )


syslog_qa_engine = SyslogQAEngine()


# @netai_tool(name="get_evidence")  # type: ignore[operator]
# def get_syslog_evidence(question: str, top_k: int = 8) -> dict[str, Any]:
#     """Retrieve ranked syslog evidence from ClickHouse events and Qdrant templates."""
#     safe_top_k = max(1, min(int(top_k), 50))
#     return syslog_qa_engine.retrieve_evidence(question=question, top_k=safe_top_k)


@netai_tool(name="syslog_get_host_syslogs")  # type: ignore[operator]
def get_host_syslogs(
    hostname: Annotated[
        str, "Hostname filter for ClickHouse syslog events (partial match)."
    ],
    severity: Annotated[int | None, "Optional severity filter (-1 to 7)."] = None,
) -> dict[str, Any]:
    """Return latest 40 ClickHouse syslog events by hostname, optionally filtered by severity."""
    return syslog_qa_engine.lookup_logs(hostname=hostname, severity=severity)
