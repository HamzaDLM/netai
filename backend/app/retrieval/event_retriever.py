from dataclasses import dataclass
import re

import httpx

from app.core.config import project_settings


@dataclass(slots=True)
class EventEvidence:
    source: str
    content: str
    score: float


class EventRetriever:
    def __init__(self) -> None:
        self.base_url = project_settings.CLICKHOUSE_URL.rstrip("/")
        self.database = project_settings.CLICKHOUSE_DB
        self.user = project_settings.CLICKHOUSE_USER
        self.password = project_settings.CLICKHOUSE_PASSWORD

    async def retrieve(
        self,
        *,
        query: str,
        ips: list[str],
        hostnames: list[str],
        top_k: int = 10,
    ) -> list[EventEvidence]:
        keywords = _extract_keywords(query)
        sql = _build_sql(
            database=self.database,
            top_k=top_k,
            lookback_seconds=project_settings.LOG_QA_LOOKBACK_SECONDS,
            ips=ips,
            hostnames=hostnames,
            keywords=keywords,
        )

        if not sql:
            return []

        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                auth=(self.user, self.password),
            ) as client:
                response = await client.post(
                    f"{self.base_url}/",
                    params={"database": self.database},
                    content=sql.encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                )
                response.raise_for_status()
                body = response.json()
        except Exception:
            return []

        evidence: list[EventEvidence] = []
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
                EventEvidence(source="clickhouse_event", content=content, score=score)
            )

        evidence.sort(key=lambda x: x.score, reverse=True)
        return evidence[:top_k]


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


def _escape_sql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _build_sql(
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

    if not where_clauses:
        return ""

    top_k_sanitized = max(1, min(int(top_k), 200))
    where_sql = " AND ".join(where_clauses)
    return (
        f"SELECT ts_unix, hostname, raw_message, template "
        f"FROM {database}.syslog_events "
        f"WHERE {where_sql} "
        f"ORDER BY ts_unix DESC "
        f"LIMIT {top_k_sanitized} "
        f"FORMAT JSON"
    )
