from typing import Annotated, Any

from haystack.tools import tool


_PRIORITY_ORDER = {
    "1 - critical": 1,
    "2 - high": 2,
    "3 - moderate": 3,
    "4 - low": 4,
    "5 - planning": 5,
}

_RISK_ORDER = {"critical": 1, "high": 2, "moderate": 3, "low": 4}

_FAKE_CIS: dict[str, dict[str, Any]] = {
    "ci-001": {
        "sys_id": "ci-001",
        "name": "edge-fw-par-01",
        "ci_class": "network_firewall",
        "ip_address": "10.10.1.1",
        "site": "Paris-DC1",
        "service": "WAN-Edge",
        "environment": "prod",
        "install_status": "in_service",
        "owned_by_group": "NetSec",
    },
    "ci-002": {
        "sys_id": "ci-002",
        "name": "core-sw-par-01",
        "ci_class": "network_switch",
        "ip_address": "10.10.1.11",
        "site": "Paris-DC1",
        "service": "DC-Core",
        "environment": "prod",
        "install_status": "in_service",
        "owned_by_group": "Network-Core",
    },
    "ci-003": {
        "sys_id": "ci-003",
        "name": "dist-rtr-nyc-01",
        "ci_class": "network_router",
        "ip_address": "10.20.1.1",
        "site": "NYC-DC1",
        "service": "WAN-Transit",
        "environment": "prod",
        "install_status": "in_service",
        "owned_by_group": "Network-Backbone",
    },
    "ci-004": {
        "sys_id": "ci-004",
        "name": "wlc-sfo-01",
        "ci_class": "wireless_controller",
        "ip_address": "10.30.1.20",
        "site": "SFO-Campus",
        "service": "Campus-Wifi",
        "environment": "prod",
        "install_status": "maintenance",
        "owned_by_group": "Network-Access",
    },
}

_FAKE_INCIDENTS: list[dict[str, Any]] = [
    {
        "number": "INC0010421",
        "state": "in_progress",
        "priority": "1 - Critical",
        "impact": "high",
        "urgency": "high",
        "major_incident": True,
        "short_description": "BGP instability on NYC transit edge",
        "description": "Transit peer flapping causes intermittent packet loss for east coast sites.",
        "service": "WAN-Transit",
        "assignment_group": "Network-Backbone",
        "assigned_to": "Carla Diaz",
        "opened_at": "2026-03-29T08:42:00Z",
        "updated_at": "2026-03-31T18:20:00Z",
        "ci_sys_id": "ci-003",
        "related_problem": "PRB000381",
        "related_change": "CHG0007721",
    },
    {
        "number": "INC0010435",
        "state": "new",
        "priority": "2 - High",
        "impact": "high",
        "urgency": "medium",
        "major_incident": False,
        "short_description": "Access port errors increasing on core-sw-par-01",
        "description": "CRC and input errors seen on TenGig1/0/48 during peak load.",
        "service": "DC-Core",
        "assignment_group": "Network-Core",
        "assigned_to": "",
        "opened_at": "2026-03-31T07:10:00Z",
        "updated_at": "2026-03-31T09:44:00Z",
        "ci_sys_id": "ci-002",
        "related_problem": "",
        "related_change": "",
    },
    {
        "number": "INC0010452",
        "state": "on_hold",
        "priority": "3 - Moderate",
        "impact": "medium",
        "urgency": "medium",
        "major_incident": False,
        "short_description": "Intermittent VPN session drops at Paris edge",
        "description": "Investigating whether timeout policy mismatch causes tunnel renegotiation.",
        "service": "WAN-Edge",
        "assignment_group": "NetSec",
        "assigned_to": "Alice Martin",
        "opened_at": "2026-03-30T15:24:00Z",
        "updated_at": "2026-03-31T16:02:00Z",
        "ci_sys_id": "ci-001",
        "related_problem": "PRB000390",
        "related_change": "CHG0007738",
    },
    {
        "number": "INC0010460",
        "state": "resolved",
        "priority": "4 - Low",
        "impact": "low",
        "urgency": "low",
        "major_incident": False,
        "short_description": "Controller maintenance notification for wlc-sfo-01",
        "description": "Planned reboot completed, APs have rejoined as expected.",
        "service": "Campus-Wifi",
        "assignment_group": "Network-Access",
        "assigned_to": "Ravi Patel",
        "opened_at": "2026-03-27T12:00:00Z",
        "updated_at": "2026-03-27T13:05:00Z",
        "ci_sys_id": "ci-004",
        "related_problem": "",
        "related_change": "CHG0007702",
    },
]

_FAKE_CHANGES: list[dict[str, Any]] = [
    {
        "number": "CHG0007721",
        "type": "emergency",
        "state": "implement",
        "risk": "high",
        "short_description": "Adjust BGP hold timers for NYC transit peers",
        "service": "WAN-Transit",
        "assignment_group": "Network-Backbone",
        "opened_by": "Carla Diaz",
        "start_at": "2026-03-31T20:00:00Z",
        "end_at": "2026-03-31T22:00:00Z",
        "ci_sys_id": "ci-003",
        "related_incidents": ["INC0010421"],
    },
    {
        "number": "CHG0007738",
        "type": "normal",
        "state": "scheduled",
        "risk": "moderate",
        "short_description": "Harden SSH ciphers on Paris edge firewall",
        "service": "WAN-Edge",
        "assignment_group": "NetSec",
        "opened_by": "Alice Martin",
        "start_at": "2026-04-02T01:00:00Z",
        "end_at": "2026-04-02T02:00:00Z",
        "ci_sys_id": "ci-001",
        "related_incidents": ["INC0010452"],
    },
    {
        "number": "CHG0007702",
        "type": "standard",
        "state": "closed",
        "risk": "low",
        "short_description": "Wireless controller monthly patch baseline",
        "service": "Campus-Wifi",
        "assignment_group": "Network-Access",
        "opened_by": "Ravi Patel",
        "start_at": "2026-03-27T11:30:00Z",
        "end_at": "2026-03-27T12:30:00Z",
        "ci_sys_id": "ci-004",
        "related_incidents": ["INC0010460"],
    },
]

_FAKE_PROBLEMS: list[dict[str, Any]] = [
    {
        "number": "PRB000381",
        "state": "investigating",
        "priority": "2 - High",
        "known_error": False,
        "short_description": "Recurring transit BGP flap under evening traffic bursts",
        "root_cause": "",
        "service": "WAN-Transit",
        "assignment_group": "Network-Backbone",
        "opened_at": "2026-03-28T09:05:00Z",
        "updated_at": "2026-03-31T18:10:00Z",
        "ci_sys_id": "ci-003",
        "related_incidents": ["INC0010421"],
        "related_changes": ["CHG0007721"],
    },
    {
        "number": "PRB000390",
        "state": "known_error",
        "priority": "3 - Moderate",
        "known_error": True,
        "short_description": "VPN rekey mismatch on legacy branch peers",
        "root_cause": "IKE policy lifetime mismatch between edge and remote peer profile",
        "service": "WAN-Edge",
        "assignment_group": "NetSec",
        "opened_at": "2026-03-25T10:50:00Z",
        "updated_at": "2026-03-31T14:02:00Z",
        "ci_sys_id": "ci-001",
        "related_incidents": ["INC0010452"],
        "related_changes": ["CHG0007738"],
    },
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _ci_for(sys_id: str | None) -> dict[str, Any] | None:
    if not sys_id:
        return None
    return _FAKE_CIS.get(sys_id)


def _enrich_with_ci(record: dict[str, Any]) -> dict[str, Any]:
    ci = _ci_for(record.get("ci_sys_id"))
    item = dict(record)
    if ci:
        item["ci"] = {
            "sys_id": ci["sys_id"],
            "name": ci["name"],
            "ci_class": ci["ci_class"],
            "service": ci["service"],
            "site": ci["site"],
            "install_status": ci["install_status"],
        }
    return item


def _sort_incidents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda row: (
            _PRIORITY_ORDER.get(_normalize(row.get("priority")), 99),
            row.get("updated_at", ""),
        ),
    )


def _sort_changes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda row: (
            _RISK_ORDER.get(_normalize(row.get("risk")), 99),
            row.get("start_at", ""),
        ),
    )


KNOWN_FAKE_CIS: list[dict[str, Any]] = [
    {
        "sys_id": ci["sys_id"],
        "name": ci["name"],
        "ip_address": ci["ip_address"],
        "service": ci["service"],
        "site": ci["site"],
    }
    for ci in _FAKE_CIS.values()
]


@tool(name="servicenow.get_known_cis")
def get_known_cis() -> list[dict[str, Any]]:
    """Return canonical fake ServiceNow CMDB CI list."""
    return KNOWN_FAKE_CIS


@tool(name="servicenow.list_incidents")
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
    """List incidents with practical filters for triage."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    items: list[dict[str, Any]] = []
    for incident in _FAKE_INCIDENTS:
        if state and _normalize(incident["state"]) != _normalize(state):
            continue
        if priority and _normalize(incident["priority"]) != _normalize(priority):
            continue
        if assignment_group and _normalize(incident["assignment_group"]) != _normalize(
            assignment_group
        ):
            continue
        if service and _normalize(incident["service"]) != _normalize(service):
            continue
        if only_major and not incident.get("major_incident", False):
            continue
        items.append(_enrich_with_ci(incident))

    ordered = _sort_incidents(items)
    result = ordered[: min(limit, 100)]
    return {"count": len(result), "incidents": result}


@tool(name="servicenow.get_incident")
def get_incident(
    incident_number: Annotated[str, "Incident number, e.g. INC0010421"],
) -> dict[str, Any]:
    """Get one incident and its linked records."""
    lookup = _normalize(incident_number)
    if not lookup:
        return {"error": "incident_number_required"}

    for incident in _FAKE_INCIDENTS:
        if _normalize(incident["number"]) == lookup:
            item = _enrich_with_ci(incident)
            linked_problem = next(
                (
                    p
                    for p in _FAKE_PROBLEMS
                    if _normalize(p["number"])
                    == _normalize(incident.get("related_problem"))
                ),
                None,
            )
            linked_change = next(
                (
                    c
                    for c in _FAKE_CHANGES
                    if _normalize(c["number"])
                    == _normalize(incident.get("related_change"))
                ),
                None,
            )
            if linked_problem:
                item["problem"] = {
                    "number": linked_problem["number"],
                    "state": linked_problem["state"],
                    "short_description": linked_problem["short_description"],
                }
            if linked_change:
                item["change_request"] = {
                    "number": linked_change["number"],
                    "state": linked_change["state"],
                    "risk": linked_change["risk"],
                    "short_description": linked_change["short_description"],
                }
            return item

    return {
        "error": f"incident_not_found:{incident_number}",
        "available_incidents": [row["number"] for row in _FAKE_INCIDENTS[:10]],
    }


@tool(name="servicenow.list_change_requests")
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
    """List change requests and related CI context."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    items: list[dict[str, Any]] = []
    for change in _FAKE_CHANGES:
        if state and _normalize(change["state"]) != _normalize(state):
            continue
        if risk and _normalize(change["risk"]) != _normalize(risk):
            continue
        if service and _normalize(change["service"]) != _normalize(service):
            continue
        if assignment_group and _normalize(change["assignment_group"]) != _normalize(
            assignment_group
        ):
            continue
        items.append(_enrich_with_ci(change))

    ordered = _sort_changes(items)
    result = ordered[: min(limit, 100)]
    return {"count": len(result), "changes": result}


@tool(name="servicenow.get_change_request")
def get_change_request(
    change_number: Annotated[str, "Change number, e.g. CHG0007721"],
) -> dict[str, Any]:
    """Get details for one change request."""
    lookup = _normalize(change_number)
    if not lookup:
        return {"error": "change_number_required"}

    for change in _FAKE_CHANGES:
        if _normalize(change["number"]) == lookup:
            return _enrich_with_ci(change)

    return {
        "error": f"change_not_found:{change_number}",
        "available_changes": [row["number"] for row in _FAKE_CHANGES[:10]],
    }


@tool(name="servicenow.list_problems")
def list_problems(
    state: Annotated[
        str | None, "Optional state filter: investigating/known_error/resolved"
    ] = None,
    priority: Annotated[str | None, "Optional priority filter"] = None,
    service: Annotated[str | None, "Optional business service filter"] = None,
    assignment_group: Annotated[str | None, "Optional assignment group filter"] = None,
    limit: Annotated[int, "Maximum number of problems to return"] = 20,
) -> dict[str, Any]:
    """List problem records with optional filters."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    items: list[dict[str, Any]] = []
    for problem in _FAKE_PROBLEMS:
        if state and _normalize(problem["state"]) != _normalize(state):
            continue
        if priority and _normalize(problem["priority"]) != _normalize(priority):
            continue
        if service and _normalize(problem["service"]) != _normalize(service):
            continue
        if assignment_group and _normalize(problem["assignment_group"]) != _normalize(
            assignment_group
        ):
            continue
        items.append(_enrich_with_ci(problem))

    ordered = _sort_incidents(items)
    result = ordered[: min(limit, 100)]
    return {"count": len(result), "problems": result}


@tool(name="servicenow.get_problem")
def get_problem(
    problem_number: Annotated[str, "Problem number, e.g. PRB000381"],
) -> dict[str, Any]:
    """Get details for one problem record."""
    lookup = _normalize(problem_number)
    if not lookup:
        return {"error": "problem_number_required"}

    for problem in _FAKE_PROBLEMS:
        if _normalize(problem["number"]) == lookup:
            return _enrich_with_ci(problem)

    return {
        "error": f"problem_not_found:{problem_number}",
        "available_problems": [row["number"] for row in _FAKE_PROBLEMS[:10]],
    }


@tool(name="servicenow.list_cis")
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
    """List CMDB CIs for network operations context."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    q = _normalize(query)
    items: list[dict[str, Any]] = []
    for ci in _FAKE_CIS.values():
        if ci_class and _normalize(ci["ci_class"]) != _normalize(ci_class):
            continue
        if site and _normalize(ci["site"]) != _normalize(site):
            continue
        if service and _normalize(ci["service"]) != _normalize(service):
            continue
        if install_status and _normalize(ci["install_status"]) != _normalize(
            install_status
        ):
            continue
        if q:
            haystack = f'{ci["name"]} {ci["ip_address"]} {ci["owned_by_group"]} {ci["service"]}'.lower()
            if q not in haystack:
                continue
        items.append(ci)

    result = items[: min(limit, 100)]
    return {"count": len(result), "cis": result}


@tool(name="servicenow.get_ci")
def get_ci(
    ci_name_or_sys_id: Annotated[str, "CI hostname/name or sys_id"],
) -> dict[str, Any]:
    """Get one CI by name or sys_id and include open record counters."""
    lookup = _normalize(ci_name_or_sys_id)
    if not lookup:
        return {"error": "ci_lookup_required"}

    matched = None
    for ci in _FAKE_CIS.values():
        if lookup in {_normalize(ci["name"]), _normalize(ci["sys_id"])}:
            matched = ci
            break
    if matched is None:
        for ci in _FAKE_CIS.values():
            haystack = f'{ci["name"]} {ci["ip_address"]} {ci["service"]}'.lower()
            if lookup in haystack:
                matched = ci
                break

    if not matched:
        return {
            "error": f"ci_not_found:{ci_name_or_sys_id}",
            "known_cis": KNOWN_FAKE_CIS,
        }

    ci_sys_id = matched["sys_id"]
    open_incidents = [
        row
        for row in _FAKE_INCIDENTS
        if row.get("ci_sys_id") == ci_sys_id
        and _normalize(row.get("state")) not in {"resolved", "closed"}
    ]
    open_changes = [
        row
        for row in _FAKE_CHANGES
        if row.get("ci_sys_id") == ci_sys_id
        and _normalize(row.get("state")) != "closed"
    ]
    open_problems = [
        row
        for row in _FAKE_PROBLEMS
        if row.get("ci_sys_id") == ci_sys_id
        and _normalize(row.get("state")) not in {"resolved", "closed"}
    ]

    return {
        **matched,
        "open_record_summary": {
            "incidents": len(open_incidents),
            "changes": len(open_changes),
            "problems": len(open_problems),
        },
        "related_records": {
            "incidents": [row["number"] for row in open_incidents],
            "changes": [row["number"] for row in open_changes],
            "problems": [row["number"] for row in open_problems],
        },
    }


@tool(name="servicenow.get_service_summary")
def get_service_summary(
    service: Annotated[str, "Business service name, e.g. WAN-Edge"],
) -> dict[str, Any]:
    """Aggregate incident/problem/change posture for one service."""
    service_lc = _normalize(service)
    if not service_lc:
        return {"error": "service_required"}

    incidents = [
        row for row in _FAKE_INCIDENTS if _normalize(row["service"]) == service_lc
    ]
    changes = [row for row in _FAKE_CHANGES if _normalize(row["service"]) == service_lc]
    problems = [
        row for row in _FAKE_PROBLEMS if _normalize(row["service"]) == service_lc
    ]
    cis = [
        row for row in _FAKE_CIS.values() if _normalize(row["service"]) == service_lc
    ]

    if not incidents and not changes and not problems and not cis:
        known_services = sorted({row["service"] for row in _FAKE_CIS.values()})
        return {
            "error": f"service_not_found:{service}",
            "known_services": known_services,
        }

    active_incidents = [
        row
        for row in incidents
        if _normalize(row.get("state")) not in {"resolved", "closed"}
    ]
    major_incidents = [row for row in active_incidents if row.get("major_incident")]
    open_changes = [row for row in changes if _normalize(row.get("state")) != "closed"]
    open_problems = [
        row
        for row in problems
        if _normalize(row.get("state")) not in {"resolved", "closed"}
    ]

    return {
        "service": service,
        "summary": {
            "ci_count": len(cis),
            "active_incidents": len(active_incidents),
            "major_incidents": len(major_incidents),
            "open_changes": len(open_changes),
            "open_problems": len(open_problems),
        },
        "active_incident_numbers": [
            row["number"] for row in _sort_incidents(active_incidents)
        ],
        "open_change_numbers": [row["number"] for row in _sort_changes(open_changes)],
        "open_problem_numbers": [
            row["number"] for row in _sort_incidents(open_problems)
        ],
    }
