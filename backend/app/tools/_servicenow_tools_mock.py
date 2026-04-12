from typing import Annotated, Any

import httpx
from haystack.tools import tool

from app.core.config import project_settings

INCIDENT_STATE_MAP = {
    "new": "1",
    "in_progress": "2",
    "on_hold": "3",
    "resolved": "6",
    "closed": "7",
    "canceled": "8",
}
CHANGE_STATE_MAP = {
    "new": "-5",
    "assess": "-4",
    "authorize": "-3",
    "scheduled": "-2",
    "implement": "-1",
    "review": "0",
    "closed": "3",
    "canceled": "4",
}
RISK_MAP = {"critical": "1", "high": "2", "moderate": "3", "low": "4"}
INSTALL_STATUS_MAP = {
    "in_service": "1",
    "retired": "7",
    "maintenance": "4",
}


class ServiceNowToolError(RuntimeError):
    pass


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _limit(value: int, *, default: int = 20, maximum: int = 100) -> int:
    if value < 1:
        return default
    return min(value, maximum)


def _to_priority(priority: str | None) -> str:
    raw = normalize(priority)
    if not raw:
        return ""
    # Accept "1", "1 - Critical", "critical"
    if raw[0].isdigit():
        return raw[0]
    if raw == "critical":
        return "1"
    if raw == "high":
        return "2"
    if raw in {"moderate", "medium"}:
        return "3"
    if raw == "low":
        return "4"
    if raw == "planning":
        return "5"
    return raw


def _map_filter(value: str | None, mapping: dict[str, str]) -> str:
    raw = normalize(value)
    if not raw:
        return ""
    return mapping.get(raw, raw)


def _join_query(clauses: list[str]) -> str:
    return "^".join(clause for clause in clauses if clause)


class ServiceNowGateway:
    """Small, readable ServiceNow Table API wrapper used by tools."""

    def __init__(self) -> None:
        if not project_settings.SERVICENOW_ENABLED:
            raise ServiceNowToolError("servicenow_disabled")
        if not project_settings.SERVICENOW_INSTANCE_URL:
            raise ServiceNowToolError("missing_servicenow_instance_url")

        api_version = normalize(project_settings.SERVICENOW_API_VERSION) or "v2"
        if api_version != "latest" and not api_version.startswith("v"):
            raise ServiceNowToolError("invalid_servicenow_api_version")

        base = project_settings.SERVICENOW_INSTANCE_URL.rstrip("/")
        self.base_url = f"{base}/api/now/{api_version}/table"
        self.timeout = project_settings.SERVICENOW_TIMEOUT_SECONDS

        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._auth: tuple[str, str] | None = None
        self._token: str | None = None

        if project_settings.SERVICENOW_ACCESS_TOKEN:
            self._token = project_settings.SERVICENOW_ACCESS_TOKEN
            self._headers["Authorization"] = f"Bearer {self._token}"
        elif (
            project_settings.SERVICENOW_USERNAME
            and project_settings.SERVICENOW_PASSWORD
        ):
            self._auth = (
                project_settings.SERVICENOW_USERNAME,
                project_settings.SERVICENOW_PASSWORD,
            )
        else:
            raise ServiceNowToolError("missing_servicenow_credentials")

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{table}"
        try:
            with httpx.Client(
                timeout=self.timeout, headers=self._headers, auth=self._auth
            ) as client:
                response = client.request(method, url, params=params)
        except Exception as exc:
            raise ServiceNowToolError(f"http_request_failed:{exc}") from exc

        try:
            payload = response.json()
        except Exception:
            payload = {}

        if response.status_code >= 400:
            if isinstance(payload, dict):
                error_body = payload.get("error", {})
                message = _string(error_body.get("message")) or _string(
                    payload.get("message")
                )
                detail = _string(error_body.get("detail"))
                joined = f"{message}:{detail}".strip(":")
            else:
                joined = response.text
            raise ServiceNowToolError(f"http_{response.status_code}:{joined}")

        if not isinstance(payload, dict):
            raise ServiceNowToolError("unexpected_response_shape")
        return payload

    def query_table(
        self,
        table: str,
        *,
        query: str = "",
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "sysparm_limit": _limit(limit),
            "sysparm_display_value": "true",
            "sysparm_exclude_reference_link": "true",
            "sysparm_suppress_pagination_header": "true",
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)

        payload = self._request("GET", table, params=params)
        result = payload.get("result", [])
        if not isinstance(result, list):
            return []
        return [row for row in result if isinstance(row, dict)]

    def get_one_by_query(
        self,
        table: str,
        *,
        query: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        items = self.query_table(table, query=query, fields=fields, limit=1)
        if not items:
            return None
        return items[0]


def error_payload(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


def gateway() -> ServiceNowGateway:
    # ServiceNow REST API Explorer currently surfaces Table API version `v2`
    # with support for choosing `latest`; this gateway accepts either.
    return ServiceNowGateway()


def _ci_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sys_id": _string(row.get("sys_id")),
        "name": _string(row.get("name")),
        "ip_address": _string(row.get("ip_address")),
        "service": _string(row.get("business_service") or row.get("service")),
        "site": _string(row.get("location")),
        "ci_class": _string(row.get("sys_class_name")),
        "install_status": _string(row.get("install_status")),
    }


def _incident_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sys_id": _string(row.get("sys_id")),
        "number": _string(row.get("number")),
        "state": _string(row.get("state")),
        "priority": _string(row.get("priority")),
        "impact": _string(row.get("impact")),
        "urgency": _string(row.get("urgency")),
        "major_incident": normalize(_string(row.get("major_incident_state")))
        not in {"", "not_major"},
        "short_description": _string(row.get("short_description")),
        "description": _string(row.get("description")),
        "service": _string(row.get("business_service")),
        "assignment_group": _string(row.get("assignment_group")),
        "assigned_to": _string(row.get("assigned_to")),
        "opened_at": _string(row.get("opened_at")),
        "updated_at": _string(row.get("sys_updated_on")),
        "ci": _string(row.get("cmdb_ci")),
        "related_problem": _string(row.get("problem_id")),
        "related_change": _string(row.get("rfc")),
    }


def _change_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sys_id": _string(row.get("sys_id")),
        "number": _string(row.get("number")),
        "type": _string(row.get("type")),
        "state": _string(row.get("state")),
        "risk": _string(row.get("risk")),
        "short_description": _string(row.get("short_description")),
        "description": _string(row.get("description")),
        "service": _string(row.get("business_service")),
        "assignment_group": _string(row.get("assignment_group")),
        "opened_by": _string(row.get("opened_by")),
        "start_at": _string(row.get("start_date")),
        "end_at": _string(row.get("end_date")),
        "ci": _string(row.get("cmdb_ci")),
        "updated_at": _string(row.get("sys_updated_on")),
    }


def _problem_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sys_id": _string(row.get("sys_id")),
        "number": _string(row.get("number")),
        "state": _string(row.get("state")),
        "priority": _string(row.get("priority")),
        "known_error": normalize(_string(row.get("known_error")))
        in {"true", "1", "yes"},
        "short_description": _string(row.get("short_description")),
        "root_cause": _string(row.get("close_notes")),
        "service": _string(row.get("business_service")),
        "assignment_group": _string(row.get("assignment_group")),
        "opened_at": _string(row.get("opened_at")),
        "updated_at": _string(row.get("sys_updated_on")),
        "ci": _string(row.get("cmdb_ci")),
    }


@tool(name="servicenow.get_known_cis")  # type: ignore[operator]
def get_known_cis() -> list[dict[str, Any]] | dict[str, Any]:
    """Return CI name/IP shortlist from ServiceNow CMDB."""
    try:
        rows = gateway().query_table(
            "cmdb_ci",
            query="install_status!=7^ORDERBYname",
            fields=["sys_id", "name", "ip_address", "location", "business_service"],
            limit=100,
        )
        return [
            {
                "sys_id": _string(row.get("sys_id")),
                "name": _string(row.get("name")),
                "ip_address": _string(row.get("ip_address")),
                "service": _string(row.get("business_service")),
                "site": _string(row.get("location")),
            }
            for row in rows
        ]
    except Exception as exc:
        return error_payload("get_known_cis", exc)


@tool(name="servicenow.list_incidents")  # type: ignore[operator]
def list_incidents(
    state: Annotated[
        str | None, "Optional state filter: new/in_progress/on_hold/resolved"
    ] = None,
    priority: Annotated[
        str | None, "Optional priority filter: e.g. 1 - Critical"
    ] = None,
    assignment_group: Annotated[str | None, "Optional assignment group filter"] = None,
    service: Annotated[str | None, "Optional business service filter"] = None,
    only_major: Annotated[bool, "Only major incidents"] = False,
    limit: Annotated[int, "Maximum number of incidents to return"] = 20,
) -> dict[str, Any]:
    """List ServiceNow incidents with practical triage filters."""
    try:
        clauses: list[str] = []
        state_value = _map_filter(state, INCIDENT_STATE_MAP)
        if state_value:
            clauses.append(f"state={state_value}")
        priority_value = _to_priority(priority)
        if priority_value:
            clauses.append(f"priority={priority_value}")
        if assignment_group:
            clauses.append(f"assignment_group.nameLIKE{assignment_group.strip()}")
        if service:
            clauses.append(f"business_service.nameLIKE{service.strip()}")
        if only_major:
            clauses.append("major_incident_state!=not_major")
        clauses.append("ORDERBYpriority")
        clauses.append("ORDERBYDESCsys_updated_on")

        rows = gateway().query_table(
            "incident",
            query=_join_query(clauses),
            fields=[
                "sys_id",
                "number",
                "state",
                "priority",
                "impact",
                "urgency",
                "major_incident_state",
                "short_description",
                "description",
                "business_service",
                "assignment_group",
                "assigned_to",
                "opened_at",
                "sys_updated_on",
                "cmdb_ci",
                "problem_id",
                "rfc",
            ],
            limit=limit,
        )
        incidents = [_incident_brief(row) for row in rows]
        return {"count": len(incidents), "incidents": incidents}
    except Exception as exc:
        return error_payload("list_incidents", exc)


@tool(name="servicenow.get_incident")  # type: ignore[operator]
def get_incident(
    incident_number: Annotated[str, "Incident number, e.g. INC0010421"],
) -> dict[str, Any]:
    """Get a single incident by number with linked record hints."""
    if not incident_number.strip():
        return {"error": "incident_number_required"}

    try:
        row = gateway().get_one_by_query(
            "incident",
            query=f"number={incident_number.strip()}",
            fields=[
                "sys_id",
                "number",
                "state",
                "priority",
                "impact",
                "urgency",
                "major_incident_state",
                "short_description",
                "description",
                "business_service",
                "assignment_group",
                "assigned_to",
                "opened_at",
                "sys_updated_on",
                "cmdb_ci",
                "problem_id",
                "rfc",
            ],
        )
        if not row:
            return {"error": f"incident_not_found:{incident_number}"}
        return _incident_brief(row)
    except Exception as exc:
        return error_payload("get_incident", exc)


@tool(name="servicenow.list_change_requests")  # type: ignore[operator]
def list_change_requests(
    state: Annotated[
        str | None, "Optional state filter: new/scheduled/implement/closed"
    ] = None,
    risk: Annotated[
        str | None, "Optional risk filter: critical/high/moderate/low"
    ] = None,
    service: Annotated[str | None, "Optional business service filter"] = None,
    assignment_group: Annotated[str | None, "Optional assignment group filter"] = None,
    limit: Annotated[int, "Maximum number of changes to return"] = 20,
) -> dict[str, Any]:
    """List ServiceNow change requests."""
    try:
        clauses: list[str] = []
        state_value = _map_filter(state, CHANGE_STATE_MAP)
        if state_value:
            clauses.append(f"state={state_value}")
        risk_value = _map_filter(risk, RISK_MAP)
        if risk_value:
            clauses.append(f"risk={risk_value}")
        if service:
            clauses.append(f"business_service.nameLIKE{service.strip()}")
        if assignment_group:
            clauses.append(f"assignment_group.nameLIKE{assignment_group.strip()}")
        clauses.append("ORDERBYrisk")
        clauses.append("ORDERBYstart_date")

        rows = gateway().query_table(
            "change_request",
            query=_join_query(clauses),
            fields=[
                "sys_id",
                "number",
                "type",
                "state",
                "risk",
                "short_description",
                "description",
                "business_service",
                "assignment_group",
                "opened_by",
                "start_date",
                "end_date",
                "cmdb_ci",
                "sys_updated_on",
            ],
            limit=limit,
        )
        changes = [_change_brief(row) for row in rows]
        return {"count": len(changes), "changes": changes}
    except Exception as exc:
        return error_payload("list_change_requests", exc)


@tool(name="servicenow.get_change_request")  # type: ignore[operator]  # noqa
def get_change_request(
    change_number: Annotated[str, "Change number, e.g. CHG0007721"],
) -> dict[str, Any]:
    """Get one change request by number."""
    if not change_number.strip():
        return {"error": "change_number_required"}

    try:
        row = gateway().get_one_by_query(
            "change_request",
            query=f"number={change_number.strip()}",
            fields=[
                "sys_id",
                "number",
                "type",
                "state",
                "risk",
                "short_description",
                "description",
                "business_service",
                "assignment_group",
                "opened_by",
                "start_date",
                "end_date",
                "cmdb_ci",
                "sys_updated_on",
            ],
        )
        if not row:
            return {"error": f"change_not_found:{change_number}"}
        return _change_brief(row)
    except Exception as exc:
        return error_payload("get_change_request", exc)


@tool(name="servicenow.list_problems")  # type: ignore[operator]
def list_problems(
    state: Annotated[
        str | None, "Optional state filter: investigating/known_error/resolved"
    ] = None,
    priority: Annotated[str | None, "Optional priority filter"] = None,
    service: Annotated[str | None, "Optional business service filter"] = None,
    assignment_group: Annotated[str | None, "Optional assignment group filter"] = None,
    limit: Annotated[int, "Maximum number of problems to return"] = 20,
) -> dict[str, Any]:
    """List ServiceNow problem records."""
    try:
        clauses: list[str] = []
        if state:
            clauses.append(f"state={state.strip()}")
        priority_value = _to_priority(priority)
        if priority_value:
            clauses.append(f"priority={priority_value}")
        if service:
            clauses.append(f"business_service.nameLIKE{service.strip()}")
        if assignment_group:
            clauses.append(f"assignment_group.nameLIKE{assignment_group.strip()}")
        clauses.append("ORDERBYpriority")
        clauses.append("ORDERBYDESCsys_updated_on")

        rows = gateway().query_table(
            "problem",
            query=_join_query(clauses),
            fields=[
                "sys_id",
                "number",
                "state",
                "priority",
                "known_error",
                "short_description",
                "close_notes",
                "business_service",
                "assignment_group",
                "opened_at",
                "sys_updated_on",
                "cmdb_ci",
            ],
            limit=limit,
        )
        problems = [_problem_brief(row) for row in rows]
        return {"count": len(problems), "problems": problems}
    except Exception as exc:
        return error_payload("list_problems", exc)


@tool(name="servicenow.get_problem")  # type: ignore[operator]
def get_problem(
    problem_number: Annotated[str, "Problem number, e.g. PRB000381"],
) -> dict[str, Any]:
    """Get one problem record by number."""
    if not problem_number.strip():
        return {"error": "problem_number_required"}

    try:
        row = gateway().get_one_by_query(
            "problem",
            query=f"number={problem_number.strip()}",
            fields=[
                "sys_id",
                "number",
                "state",
                "priority",
                "known_error",
                "short_description",
                "close_notes",
                "business_service",
                "assignment_group",
                "opened_at",
                "sys_updated_on",
                "cmdb_ci",
            ],
        )
        if not row:
            return {"error": f"problem_not_found:{problem_number}"}
        return _problem_brief(row)
    except Exception as exc:
        return error_payload("get_problem", exc)


@tool(name="servicenow.list_cis")  # type: ignore[operator]
def list_cis(
    ci_class: Annotated[
        str | None, "Optional class filter: network_firewall/network_switch/..."
    ] = None,
    site: Annotated[str | None, "Optional site filter"] = None,
    service: Annotated[str | None, "Optional service filter"] = None,
    install_status: Annotated[str | None, "Optional install status filter"] = None,
    query: Annotated[str | None, "Optional free-text CI query (name/ip/group)"] = None,
    limit: Annotated[int, "Maximum number of CIs to return"] = 50,
) -> dict[str, Any]:
    """List CIs from CMDB with common filters."""
    try:
        clauses: list[str] = []
        if ci_class:
            clauses.append(f"sys_class_name={ci_class.strip()}")
        if site:
            clauses.append(f"location.nameLIKE{site.strip()}")
        if service:
            clauses.append(f"business_service.nameLIKE{service.strip()}")
        install_value = _map_filter(install_status, INSTALL_STATUS_MAP)
        if install_value:
            clauses.append(f"install_status={install_value}")
        if query:
            q = query.strip()
            clauses.append(f"nameLIKE{q}^ORip_addressLIKE{q}^ORfqdnLIKE{q}")
        clauses.append("ORDERBYname")

        rows = gateway().query_table(
            "cmdb_ci",
            query=_join_query(clauses),
            fields=[
                "sys_id",
                "name",
                "sys_class_name",
                "ip_address",
                "fqdn",
                "location",
                "business_service",
                "install_status",
                "owned_by",
            ],
            limit=limit,
        )
        cis = [_ci_brief(row) for row in rows]
        return {"count": len(cis), "cis": cis}
    except Exception as exc:
        return error_payload("list_cis", exc)


@tool(name="servicenow.get_ci")  # type: ignore[operator]
def get_ci(
    ci_name_or_sys_id: Annotated[str, "CI hostname/name or sys_id"],
) -> dict[str, Any]:
    """Get one CI and summarize open incident/change/problem counts."""
    target = ci_name_or_sys_id.strip()
    if not target:
        return {"error": "ci_lookup_required"}

    try:
        ci_row = gateway().get_one_by_query(
            "cmdb_ci",
            query=f"sys_id={target}^ORname={target}^ORip_address={target}",
            fields=[
                "sys_id",
                "name",
                "sys_class_name",
                "ip_address",
                "fqdn",
                "location",
                "business_service",
                "install_status",
                "owned_by",
            ],
        )
        if not ci_row:
            return {"error": f"ci_not_found:{ci_name_or_sys_id}"}

        ci_sys_id = _string(ci_row.get("sys_id"))
        if not ci_sys_id:
            return {"error": "ci_sys_id_missing"}

        incidents = gateway().query_table(
            "incident",
            query=f"cmdb_ci={ci_sys_id}^stateNOT IN6,7,8",
            fields=["number"],
            limit=100,
        )
        changes = gateway().query_table(
            "change_request",
            query=f"cmdb_ci={ci_sys_id}^state!=3^state!=4",
            fields=["number"],
            limit=100,
        )
        problems = gateway().query_table(
            "problem",
            query=f"cmdb_ci={ci_sys_id}^state!=7",
            fields=["number"],
            limit=100,
        )

        return {
            **_ci_brief(ci_row),
            "open_record_summary": {
                "incidents": len(incidents),
                "changes": len(changes),
                "problems": len(problems),
            },
            "related_records": {
                "incidents": [_string(row.get("number")) for row in incidents],
                "changes": [_string(row.get("number")) for row in changes],
                "problems": [_string(row.get("number")) for row in problems],
            },
        }
    except Exception as exc:
        return error_payload("get_ci", exc)


@tool(name="servicenow.get_service_summary")  # type: ignore[operator]
def get_service_summary(
    service: Annotated[str, "Business service name, e.g. WAN-Edge"],
) -> dict[str, Any]:
    """Aggregate service-level ticket posture across incident/change/problem."""
    target = service.strip()
    if not target:
        return {"error": "service_required"}

    try:
        active_incidents = gateway().query_table(
            "incident",
            query=f"business_service.nameLIKE{target}^stateNOT IN6,7,8",
            fields=["number"],
            limit=100,
        )
        major_incidents = gateway().query_table(
            "incident",
            query=f"business_service.nameLIKE{target}^major_incident_state!=not_major^stateNOT IN6,7,8",
            fields=["number"],
            limit=100,
        )
        open_changes = gateway().query_table(
            "change_request",
            query=f"business_service.nameLIKE{target}^state!=3^state!=4",
            fields=["number"],
            limit=100,
        )
        open_problems = gateway().query_table(
            "problem",
            query=f"business_service.nameLIKE{target}^state!=7",
            fields=["number"],
            limit=100,
        )
        cis = gateway().query_table(
            "cmdb_ci",
            query=f"business_service.nameLIKE{target}",
            fields=["sys_id"],
            limit=100,
        )

        return {
            "service": target,
            "summary": {
                "ci_count": len(cis),
                "active_incidents": len(active_incidents),
                "major_incidents": len(major_incidents),
                "open_changes": len(open_changes),
                "open_problems": len(open_problems),
            },
            "active_incident_numbers": [
                _string(row.get("number")) for row in active_incidents
            ],
            "open_change_numbers": [_string(row.get("number")) for row in open_changes],
            "open_problem_numbers": [
                _string(row.get("number")) for row in open_problems
            ],
        }
    except Exception as exc:
        return error_payload("get_service_summary", exc)
