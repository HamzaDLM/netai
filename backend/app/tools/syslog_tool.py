"""Read-only syslog queries backed by ClickHouse."""

from typing import Annotated

from haystack.components.agents import State

from app.core.config import project_settings
from app.infrastructure import clients_from_state
from app.tools import netai_tool

TOOL_GROUP_PROMPT = """
Syslog provides timestamped device messages useful for incident evidence and event
sequencing. Query a specific hostname and use the narrowest useful severity/time
scope. Treat raw messages as device-emitted evidence, preserve their timestamps and
severity, and distinguish repeated symptoms from a single event. Logs can reveal
correlation and ordering but do not automatically establish causality; compare them
with monitoring events, live network state, and recent configuration changes.
""".strip()

SYSLOG_HOST_LOG_LIMIT = 40


def _escape_sql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _normalize_severity(value: int | None) -> int | None:
    if value is None:
        return None
    severity = int(value)
    if severity < -1 or severity > 7:
        raise ValueError("severity_out_of_range:-1_to_7")
    return severity


def _build_host_logs_sql(
    *,
    database: str,
    hostname: str,
    severity: int | None,
) -> str:
    safe_hostname = _escape_sql(hostname.lower())
    clauses = [f"positionCaseInsensitiveUTF8(hostname, '{safe_hostname}') > 0"]
    if severity is not None:
        clauses.append(f"severity = {severity}")
    return (
        "SELECT event_id, ts_unix, hostname, vendor, facility, severity, "
        "event_code, raw_message, normalized_message, template "
        f"FROM {database}.syslog_events "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY ts_unix DESC "
        f"LIMIT {SYSLOG_HOST_LOG_LIMIT} FORMAT JSON"
    )


def _empty_result(
    hostname: str,
    severity: int | None,
    *,
    error: str,
) -> dict[str, object]:
    return {
        "hostname": hostname,
        "severity": severity,
        "limit": SYSLOG_HOST_LOG_LIMIT,
        "count": 0,
        "logs": [],
        "error": error,
    }


@netai_tool(name="syslog_get_host_syslogs")  # type: ignore[operator]
async def get_host_syslogs(
    agent_state: State,
    hostname: Annotated[
        str, "Hostname filter for ClickHouse syslog events (partial match)."
    ],
    severity: Annotated[int | None, "Optional severity filter (-1 to 7)."] = None,
) -> dict[str, object]:
    """Return the latest 40 ClickHouse syslog events for a hostname."""

    normalized_hostname = hostname.strip()
    if not normalized_hostname:
        return _empty_result("", severity, error="hostname_required")

    try:
        normalized_severity = _normalize_severity(severity)
    except ValueError as exc:
        return _empty_result(normalized_hostname, severity, error=str(exc))

    sql = _build_host_logs_sql(
        database=project_settings.CLICKHOUSE_DB,
        hostname=normalized_hostname,
        severity=normalized_severity,
    )
    try:
        response = await clients_from_state(agent_state).request(
            "clickhouse",
            "POST",
            f"{project_settings.CLICKHOUSE_URL.rstrip('/')}/",
            params={"database": project_settings.CLICKHOUSE_DB},
            content=sql,
            headers={"Content-Type": "text/plain"},
            auth=(
                project_settings.CLICKHOUSE_USER,
                project_settings.CLICKHOUSE_PASSWORD,
            ),
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return _empty_result(
            normalized_hostname,
            normalized_severity,
            error=f"clickhouse_query_failed:{exc}",
        )

    rows = payload.get("data", []) if isinstance(payload, dict) else []
    logs = [row for row in rows if isinstance(row, dict)]
    return {
        "hostname": normalized_hostname,
        "severity": normalized_severity,
        "limit": SYSLOG_HOST_LOG_LIMIT,
        "count": len(logs),
        "logs": logs,
    }
