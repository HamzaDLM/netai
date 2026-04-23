from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from typing import Annotated, Any

from app.tools import netai_tool

SEVERITY_ORDER = {
    "not_classified": 0,
    "information": 1,
    "warning": 2,
    "average": 3,
    "high": 4,
    "disaster": 5,
}

DEFAULT_LIMIT = 100
DEFAULT_HOURS = 24
DEFAULT_MIN_SEVERITY = "average"
MAX_LIMIT = 1000


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def clamp_limit(limit: int | None, default: int = DEFAULT_LIMIT) -> int:
    if limit is None:
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return 1
    return min(value, MAX_LIMIT)


def parse_iso(value: str | None) -> datetime:
    text = (value or "").strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def hours_ago(hours: int | float | None) -> datetime:
    try:
        parsed = float(hours if hours is not None else DEFAULT_HOURS)
    except (TypeError, ValueError):
        parsed = float(DEFAULT_HOURS)
    if parsed <= 0:
        parsed = float(DEFAULT_HOURS)
    return datetime.now(tz=UTC) - timedelta(hours=parsed)


def matches_pattern(value: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    value_lc = value.lower()
    for pattern in patterns:
        pattern_lc = pattern.lower().strip()
        if not pattern_lc:
            continue
        if "*" in pattern_lc or "?" in pattern_lc:
            if fnmatch(value_lc, pattern_lc):
                return True
        elif pattern_lc in value_lc:
            return True
    return False


def parse_tags_filter(tags: list[str] | None) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {}
    for raw in tags or []:
        text = (raw or "").strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            parsed[normalize(key)] = value.strip()
        else:
            parsed[normalize(text)] = None
    return parsed


def severity_threshold(min_severity: str | None) -> int:
    sev = normalize(min_severity) or DEFAULT_MIN_SEVERITY
    return SEVERITY_ORDER.get(sev, SEVERITY_ORDER[DEFAULT_MIN_SEVERITY])


def summarize_status(host: dict[str, Any]) -> str:
    if host["maintenance"]:
        return "maintenance"
    return host["status"]


NOW = datetime.now(tz=UTC)


def ts(hours_back: float) -> str:
    return (NOW - timedelta(hours=hours_back)).isoformat().replace("+00:00", "Z")


def metric(
    itemid: str,
    key: str,
    name: str,
    value: float | int,
    units: str,
    value_type: str = "0",
    state: str = "0",
    status: str = "0",
    error: str = "",
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    for offset in range(6):
        numeric = float(value) if isinstance(value, (int, float)) else 0.0
        history.append(
            {
                "clock": ts(offset + 1),
                "value": round(max(numeric - (offset * 0.7), 0), 3),
            }
        )
    return {
        "itemid": itemid,
        "key": key,
        "name": name,
        "lastvalue": value,
        "units": units,
        "lastclock": ts(0.2),
        "value_type": value_type,
        "state": state,
        "status": status,
        "error": error,
        "history": history,
    }


FAKE_HOSTS: dict[str, dict[str, Any]] = {
    "edge-fw-par-01": {
        "hostid": "10001",
        "hostname": "edge-fw-par-01",
        "display_name": "Paris Edge Firewall",
        "ip": "10.10.1.1",
        "site": "Paris-DC1",
        "status": "up",
        "maintenance": False,
        "groups": ["Firewalls", "Edge", "Paris"],
        "tags": {"environment": "prod", "role": "edge-firewall", "tier": "critical"},
        "availability": {
            "agent": "available",
            "snmp": "available",
            "ipmi": "unknown",
            "jmx": "unknown",
            "active": "available",
        },
        "interfaces": [
            {
                "interfaceid": "20011",
                "name": "wan1",
                "ip": "10.10.1.1",
                "dns": "",
                "port": "10050",
                "type": "agent",
                "main": True,
                "oper_status": "up",
                "error": "",
            },
            {
                "interfaceid": "20012",
                "name": "snmp",
                "ip": "10.10.1.1",
                "dns": "",
                "port": "161",
                "type": "snmp",
                "main": False,
                "oper_status": "up",
                "error": "",
            },
        ],
        "inventory": {
            "vendor": "Fortinet",
            "model": "FortiGate 200F",
            "os": "FortiOS 7.0.13",
            "serialno_a": "FGT200F-AAA01",
        },
        "macros": [
            {"macro": "{$SITE}", "value": "PAR", "description": "Site code"},
            {"macro": "{$ROLE}", "value": "edge-fw", "description": "Role"},
        ],
        "templates": [
            {
                "templateid": "30011",
                "hostname": "tpl-fortigate-base",
                "name": "FortiGate Base",
            },
            {
                "templateid": "30012",
                "hostname": "tpl-icmp",
                "name": "ICMP Availability",
            },
        ],
        "triggers": [
            {
                "triggerid": "40011",
                "description": "VPN tunnel packet loss on branch-sfo",
                "severity": "warning",
                "enabled": True,
                "last_change": ts(1.7),
                "expression": "min(/edge-fw-par-01/vpn.loss,5m)>5",
                "recovery_expression": "max(/edge-fw-par-01/vpn.loss,5m)<1",
                "state": "0",
                "error": "",
                "value": "1",
                "dependencies": [],
                "tags": [{"tag": "scope", "value": "vpn"}],
            }
        ],
        "problems": [
            {
                "eventid": "70011",
                "triggerid": "40011",
                "name": "VPN tunnel packet loss on branch-sfo",
                "severity": "warning",
                "status": "active",
                "since": ts(1.7),
                "acknowledged": True,
                "suppressed": False,
            }
        ],
        "metrics": [
            metric("50011", "cpu.util", "CPU utilization", 41.3, "%"),
            metric("50012", "memory.util", "Memory utilization", 68.1, "%"),
            metric("50013", "net.if.in[wan1]", "WAN In", 520.2, "Mbps"),
            metric("50014", "net.if.out[wan1]", "WAN Out", 469.1, "Mbps"),
            metric("50015", "icmppingloss", "ICMP packet loss", 0.0, "%"),
        ],
    },
    "dist-rtr-nyc-01": {
        "hostid": "10003",
        "hostname": "dist-rtr-nyc-01",
        "display_name": "NYC Distribution Router 01",
        "ip": "10.20.1.1",
        "site": "NYC-DC1",
        "status": "up",
        "maintenance": False,
        "groups": ["Routers", "Distribution", "NYC"],
        "tags": {"environment": "prod", "role": "distribution-router", "tier": "high"},
        "availability": {
            "agent": "unavailable",
            "snmp": "available",
            "ipmi": "unknown",
            "jmx": "unknown",
            "active": "available",
        },
        "interfaces": [
            {
                "interfaceid": "20031",
                "name": "xe-0/0/0",
                "ip": "10.20.1.1",
                "dns": "",
                "port": "10050",
                "type": "agent",
                "main": True,
                "oper_status": "up",
                "error": "",
            },
            {
                "interfaceid": "20032",
                "name": "ae2",
                "ip": "10.20.1.1",
                "dns": "",
                "port": "161",
                "type": "snmp",
                "main": False,
                "oper_status": "down",
                "error": "CRC errors above threshold",
            },
        ],
        "inventory": {
            "vendor": "Juniper",
            "model": "MX204",
            "os": "Junos 23.2R2",
            "serialno_a": "JNPR-MX204-01",
        },
        "macros": [
            {"macro": "{$SITE}", "value": "NYC", "description": "Site code"},
            {"macro": "{$ROLE}", "value": "dist-rtr", "description": "Role"},
        ],
        "templates": [
            {
                "templateid": "30031",
                "hostname": "tpl-juniper-base",
                "name": "Juniper Base",
            },
            {"templateid": "30032", "hostname": "tpl-bgp", "name": "BGP Monitoring"},
        ],
        "triggers": [
            {
                "triggerid": "40021",
                "description": "BGP peer flapping toward ISP-B",
                "severity": "average",
                "enabled": True,
                "last_change": ts(2.4),
                "expression": "last(/dist-rtr-nyc-01/bgp.peer.down)>0",
                "recovery_expression": "last(/dist-rtr-nyc-01/bgp.peer.down)=0",
                "state": "0",
                "error": "",
                "value": "1",
                "dependencies": [],
                "tags": [{"tag": "scope", "value": "bgp"}],
            }
        ],
        "problems": [
            {
                "eventid": "70021",
                "triggerid": "40021",
                "name": "BGP peer flapping toward ISP-B",
                "severity": "average",
                "status": "active",
                "since": ts(2.4),
                "acknowledged": False,
                "suppressed": False,
            }
        ],
        "metrics": [
            metric("50031", "cpu.util", "CPU utilization", 76.4, "%"),
            metric("50032", "memory.util", "Memory utilization", 73.8, "%"),
            metric(
                "50033",
                "bgp.peer.count.down",
                "BGP peers down",
                1,
                "peers",
                value_type="3",
            ),
            metric("50034", "net.if.in[ae2]", "AE2 In", 18210, "Mbps"),
            metric(
                "50035",
                "net.if.errors[ae2]",
                "AE2 Errors",
                152,
                "errors",
                value_type="3",
                state="1",
                error="High error counter",
            ),
        ],
    },
    "wlc-sfo-01": {
        "hostid": "10004",
        "hostname": "wlc-sfo-01",
        "display_name": "SFO Wireless Controller",
        "ip": "10.30.1.20",
        "site": "SFO-Campus",
        "status": "maintenance",
        "maintenance": True,
        "groups": ["Wireless", "Controllers", "SFO"],
        "tags": {
            "environment": "prod",
            "role": "wireless-controller",
            "tier": "medium",
        },
        "availability": {
            "agent": "unknown",
            "snmp": "unknown",
            "ipmi": "unknown",
            "jmx": "unknown",
            "active": "unknown",
        },
        "interfaces": [
            {
                "interfaceid": "20041",
                "name": "uplink1",
                "ip": "10.30.1.20",
                "dns": "",
                "port": "161",
                "type": "snmp",
                "main": True,
                "oper_status": "down",
                "error": "Device in maintenance",
            }
        ],
        "inventory": {
            "vendor": "Aruba",
            "model": "Aruba 7210",
            "os": "ArubaOS 8.11.2.0",
            "serialno_a": "ARUBA-7210-77",
        },
        "macros": [
            {"macro": "{$SITE}", "value": "SFO", "description": "Site code"},
        ],
        "templates": [
            {
                "templateid": "30041",
                "hostname": "tpl-wireless",
                "name": "Wireless Controller",
            },
        ],
        "triggers": [
            {
                "triggerid": "40031",
                "description": "Host unavailable by ICMP",
                "severity": "high",
                "enabled": True,
                "last_change": ts(4.9),
                "expression": "last(/wlc-sfo-01/icmpping)=0",
                "recovery_expression": "last(/wlc-sfo-01/icmpping)=1",
                "state": "0",
                "error": "",
                "value": "1",
                "dependencies": [],
                "tags": [{"tag": "scope", "value": "availability"}],
            }
        ],
        "problems": [
            {
                "eventid": "70031",
                "triggerid": "40031",
                "name": "Host unavailable by ICMP",
                "severity": "high",
                "status": "active",
                "since": ts(4.9),
                "acknowledged": True,
                "suppressed": True,
            }
        ],
        "metrics": [
            metric("50041", "cpu.util", "CPU utilization", 0.0, "%"),
            metric("50042", "memory.util", "Memory utilization", 0.0, "%"),
            metric("50043", "icmpping", "ICMP ping", 0, "bool", value_type="3"),
        ],
    },
    "vpn-gw-lon-01": {
        "hostid": "10006",
        "hostname": "vpn-gw-lon-01",
        "display_name": "London VPN Gateway 01",
        "ip": "10.40.1.5",
        "site": "LON-DC1",
        "status": "down",
        "maintenance": False,
        "groups": ["VPN", "Gateways", "London"],
        "tags": {"environment": "prod", "role": "vpn-gateway", "tier": "critical"},
        "availability": {
            "agent": "unavailable",
            "snmp": "unavailable",
            "ipmi": "unknown",
            "jmx": "unknown",
            "active": "unavailable",
        },
        "interfaces": [
            {
                "interfaceid": "20061",
                "name": "ethernet1/1",
                "ip": "10.40.1.5",
                "dns": "",
                "port": "161",
                "type": "snmp",
                "main": True,
                "oper_status": "down",
                "error": "No response",
            }
        ],
        "inventory": {
            "vendor": "Palo Alto",
            "model": "PA-3220",
            "os": "PAN-OS 11.0.4",
            "serialno_a": "PA-3220-15",
        },
        "macros": [
            {"macro": "{$SITE}", "value": "LON", "description": "Site code"},
        ],
        "templates": [
            {"templateid": "30061", "hostname": "tpl-vpn-gw", "name": "VPN Gateway"},
        ],
        "triggers": [
            {
                "triggerid": "40051",
                "description": "Host unreachable",
                "severity": "disaster",
                "enabled": True,
                "last_change": ts(0.8),
                "expression": "last(/vpn-gw-lon-01/icmpping)=0",
                "recovery_expression": "last(/vpn-gw-lon-01/icmpping)=1",
                "state": "0",
                "error": "",
                "value": "1",
                "dependencies": [],
                "tags": [{"tag": "scope", "value": "availability"}],
            },
            {
                "triggerid": "40052",
                "description": "All VPN tunnels down",
                "severity": "high",
                "enabled": True,
                "last_change": ts(0.78),
                "expression": "last(/vpn-gw-lon-01/vpn.tunnel.up)=0",
                "recovery_expression": "last(/vpn-gw-lon-01/vpn.tunnel.up)>0",
                "state": "0",
                "error": "",
                "value": "1",
                "dependencies": [
                    {"triggerid": "40051", "description": "Host unreachable"}
                ],
                "tags": [{"tag": "scope", "value": "vpn"}],
            },
        ],
        "problems": [
            {
                "eventid": "70051",
                "triggerid": "40051",
                "name": "Host unreachable",
                "severity": "disaster",
                "status": "active",
                "since": ts(0.8),
                "acknowledged": False,
                "suppressed": False,
            },
            {
                "eventid": "70052",
                "triggerid": "40052",
                "name": "All VPN tunnels down",
                "severity": "high",
                "status": "active",
                "since": ts(0.78),
                "acknowledged": False,
                "suppressed": False,
            },
            {
                "eventid": "70053",
                "triggerid": "40052",
                "name": "Tunnel degraded",
                "severity": "average",
                "status": "resolved",
                "since": ts(8.2),
                "acknowledged": True,
                "suppressed": False,
            },
        ],
        "metrics": [
            metric("50061", "cpu.util", "CPU utilization", 0.0, "%"),
            metric("50062", "memory.util", "Memory utilization", 0.0, "%"),
            metric("50063", "icmpping", "ICMP ping", 0, "bool", value_type="3"),
            metric(
                "50064", "vpn.tunnel.up", "VPN tunnels up", 0, "tunnels", value_type="3"
            ),
        ],
    },
}


MAINTENANCE_WINDOWS = [
    {
        "maintenanceid": "80041",
        "name": "SFO wireless maintenance",
        "active_since": ts(5.5),
        "active_till": ts(-2.0),
        "description": "Planned controller maintenance",
        "maintenance_type": "0",
        "hosts": ["10004"],
        "tags": [{"tag": "window", "value": "planned", "operator": "0"}],
    }
]


PROXIES = [
    {
        "proxyid": "90001",
        "name": "proxy-paris-01",
        "status": "online",
        "last_seen": ts(0.1),
        "version": "7.0.2",
        "compatibility": "full",
        "hostids": ["10001", "10003"],
    },
    {
        "proxyid": "90002",
        "name": "proxy-london-01",
        "status": "degraded",
        "last_seen": ts(0.6),
        "version": "7.0.2",
        "compatibility": "full",
        "hostids": ["10006"],
    },
]


AUDIT_LOG = [
    {
        "auditid": "91001",
        "clock": ts(1.1),
        "actor": "netops.automation",
        "action": "trigger.update",
        "ip": "10.0.1.25",
        "resource_type": "trigger",
        "resource_name": "All VPN tunnels down",
        "details": "Adjusted expression threshold",
    },
    {
        "auditid": "91002",
        "clock": ts(3.3),
        "actor": "noc.engineer",
        "action": "maintenance.create",
        "ip": "10.0.2.12",
        "resource_type": "maintenance",
        "resource_name": "SFO wireless maintenance",
        "details": "Created recurring weekly window",
    },
]


def host_brief(host: dict[str, Any]) -> dict[str, Any]:
    return {
        "hostid": host["hostid"],
        "hostname": host["hostname"],
        "display_name": host["display_name"],
        "ip": host["ip"],
        "site": host["site"],
        "status": summarize_status(host),
        "maintenance": host["maintenance"],
        "groups": host["groups"],
        "tags": host["tags"],
        "availability": host["availability"],
        "interfaces": host["interfaces"],
        "last_seen": ts(0.2),
    }


def known_hosts() -> list[dict[str, Any]]:
    return [
        {
            "hostname": host["hostname"],
            "display_name": host["display_name"],
            "ip": host["ip"],
            "site": host["site"],
        }
        for host in FAKE_HOSTS.values()
    ]


def resolve_host(hostname_or_ip: str) -> dict[str, Any] | None:
    lookup = normalize(hostname_or_ip)
    if not lookup:
        return None

    for host in FAKE_HOSTS.values():
        if lookup in {normalize(host["hostname"]), normalize(host["ip"])}:
            return host

    for host in FAKE_HOSTS.values():
        haystack = f"{host['hostname']} {host['display_name']} {host['ip']}".lower()
        if lookup in haystack:
            return host
    return None


def host_not_found(hostname_or_ip: str, tool_name: str) -> dict[str, Any]:
    return {
        "error": f"host_not_found:{hostname_or_ip}",
        "known_hosts": known_hosts(),
        "tool": tool_name,
    }


def lookup_trigger(trigger_text: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    query = normalize(trigger_text)
    for host in FAKE_HOSTS.values():
        for trigger in host["triggers"]:
            if query == normalize(trigger["triggerid"]):
                return host, trigger
    for host in FAKE_HOSTS.values():
        for trigger in host["triggers"]:
            if query in normalize(trigger["description"]):
                return host, trigger
    return None


def build_problem_row(host: dict[str, Any], problem: dict[str, Any]) -> dict[str, Any]:
    trigger = next(
        (
            entry
            for entry in host["triggers"]
            if entry["triggerid"] == problem["triggerid"]
        ),
        None,
    )
    return {
        "eventid": problem["eventid"],
        "hostname": host["hostname"],
        "host_display_name": host["display_name"],
        "name": problem["name"],
        "severity": problem["severity"],
        "status": problem["status"],
        "since": problem["since"],
        "acknowledged": problem["acknowledged"],
        "suppressed": problem["suppressed"],
        "trigger": trigger,
        "last_event": {
            "eventid": problem["eventid"],
            "clock": problem["since"],
        },
    }


def collect_problems(
    *,
    hostname_or_ip: str | None = None,
    group: str | None = None,
    min_severity: str | None = DEFAULT_MIN_SEVERITY,
    hours: int | float | None = DEFAULT_HOURS,
    unacknowledged_only: bool = False,
    unsuppressed_only: bool = True,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    host_filter = resolve_host(hostname_or_ip) if hostname_or_ip else None
    if hostname_or_ip and not host_filter:
        return []

    group_lc = normalize(group)
    threshold = severity_threshold(min_severity)
    since_dt = hours_ago(hours)

    rows: list[dict[str, Any]] = []
    for host in FAKE_HOSTS.values():
        if host_filter and host["hostid"] != host_filter["hostid"]:
            continue
        if group_lc and group_lc not in {normalize(item) for item in host["groups"]}:
            continue

        for problem in host["problems"]:
            if SEVERITY_ORDER.get(normalize(problem["severity"]), 0) < threshold:
                continue
            if active_only and problem["status"] != "active":
                continue
            if unacknowledged_only and problem["acknowledged"]:
                continue
            if unsuppressed_only and problem["suppressed"]:
                continue
            if parse_iso(problem["since"]) < since_dt:
                continue
            rows.append(build_problem_row(host, problem))

    rows.sort(
        key=lambda row: (
            SEVERITY_ORDER.get(normalize(str(row.get("severity"))), 0),
            parse_iso(str(row.get("since"))),
        ),
        reverse=True,
    )
    return rows


def collect_events(
    *,
    hostname_or_ip: str | None = None,
    problem_event_id: str | None = None,
    hours: int | float | None = DEFAULT_HOURS,
    include_ok_events: bool = True,
) -> list[dict[str, Any]]:
    since_dt = hours_ago(hours)
    host_filter = resolve_host(hostname_or_ip) if hostname_or_ip else None
    if hostname_or_ip and not host_filter:
        return []

    trigger_filter: str | None = None
    if problem_event_id:
        for host in FAKE_HOSTS.values():
            for problem in host["problems"]:
                if problem["eventid"] == problem_event_id:
                    trigger_filter = problem["triggerid"]
                    break

    events: list[dict[str, Any]] = []
    for host in FAKE_HOSTS.values():
        if host_filter and host_filter["hostid"] != host["hostid"]:
            continue
        for problem in host["problems"]:
            if trigger_filter and trigger_filter != problem["triggerid"]:
                continue
            event_time = parse_iso(problem["since"])
            if event_time < since_dt:
                continue
            events.append(
                {
                    "eventid": problem["eventid"],
                    "hostname": host["hostname"],
                    "host_display_name": host["display_name"],
                    "name": problem["name"],
                    "severity": problem["severity"],
                    "kind": "problem",
                    "acknowledged": problem["acknowledged"],
                    "clock": problem["since"],
                    "objectid": problem["triggerid"],
                }
            )
            if include_ok_events and problem["status"] == "resolved":
                events.append(
                    {
                        "eventid": f"ok-{problem['eventid']}",
                        "hostname": host["hostname"],
                        "host_display_name": host["display_name"],
                        "name": f"RECOVERY: {problem['name']}",
                        "severity": problem["severity"],
                        "kind": "ok",
                        "acknowledged": True,
                        "clock": ts(0.4),
                        "objectid": problem["triggerid"],
                    }
                )

    events.sort(key=lambda row: parse_iso(str(row["clock"])), reverse=True)
    return events


def collect_metrics(
    host: dict[str, Any], key_patterns: list[str] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_entry in host["metrics"]:
        if not matches_pattern(metric_entry["key"], key_patterns):
            continue
        rows.append(
            {
                "itemid": metric_entry["itemid"],
                "name": metric_entry["name"],
                "key": metric_entry["key"],
                "value": metric_entry["lastvalue"],
                "unit": metric_entry["units"],
                "last_clock": metric_entry["lastclock"],
                "enabled": metric_entry["status"] == "0",
                "state": metric_entry["state"],
                "error": metric_entry["error"],
                "value_type": metric_entry["value_type"],
            }
        )
    rows.sort(key=lambda row: parse_iso(str(row["last_clock"])), reverse=True)
    return rows


@netai_tool(name="zabbix_get_hosts")  # type: ignore[operator]
def get_hosts(
    name: Annotated[str | None, "Optional hostname/display-name filter"] = None,
    group: Annotated[str | None, "Optional host-group filter"] = None,
    tags: Annotated[
        list[str] | None,
        "Optional tag filters as ['key=value', 'role']; all entries must match.",
    ] = None,
    status: Annotated[str | None, "Optional status filter: up/down/maintenance"] = None,
    maintenance: Annotated[bool | None, "Optional maintenance filter"] = None,
    limit: Annotated[int, "Maximum number of hosts to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    name_lc = normalize(name)
    group_lc = normalize(group)
    status_lc = normalize(status)
    tag_filter = parse_tags_filter(tags)

    rows: list[dict[str, Any]] = []
    for host in FAKE_HOSTS.values():
        brief = host_brief(host)
        haystack = f"{brief['hostname']} {brief['display_name']} {brief['ip']}".lower()
        if name_lc and name_lc not in haystack:
            continue
        if group_lc and group_lc not in {normalize(item) for item in brief["groups"]}:
            continue
        if status_lc and status_lc != normalize(str(brief["status"])):
            continue
        if maintenance is not None and bool(brief["maintenance"]) != maintenance:
            continue

        if tag_filter:
            tags_map = {normalize(k): str(v) for k, v in brief["tags"].items()}
            mismatch = False
            for key, expected in tag_filter.items():
                if key not in tags_map:
                    mismatch = True
                    break
                if expected is not None and tags_map[key] != expected:
                    mismatch = True
                    break
            if mismatch:
                continue

        rows.append(brief)

    rows.sort(key=lambda row: str(row["hostname"]))
    return {
        "count": len(rows),
        "filters": {
            "name": name,
            "group": group,
            "tags": tags or [],
            "status": status,
            "maintenance": maintenance,
        },
        "hosts": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_host_details")  # type: ignore[operator]
def get_host_details(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_host_details")

    return {
        **host_brief(host),
        "inventory": host["inventory"],
        "vendor": host["inventory"].get("vendor", ""),
        "model": host["inventory"].get("model", ""),
        "os": host["inventory"].get("os", ""),
        "interfaces": host["interfaces"],
        "templates": host["templates"],
        "macros": host["macros"],
    }


@netai_tool(name="zabbix_get_host_interfaces")  # type: ignore[operator]
def get_host_interfaces(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    only_problematic: Annotated[
        bool,
        "If true, include only unavailable interfaces or interfaces with errors.",
    ] = False,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_host_interfaces")

    interfaces = host["interfaces"]
    if only_problematic:
        interfaces = [
            iface
            for iface in interfaces
            if iface["oper_status"] != "up" or bool(iface["error"])
        ]

    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "count": len(interfaces),
        "interfaces": interfaces,
    }


@netai_tool(name="zabbix_get_host_groups")  # type: ignore[operator]
def get_host_groups() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for host in FAKE_HOSTS.values():
        for group in host["groups"]:
            counts[group] = counts.get(group, 0) + 1

    rows = [
        {"groupid": f"g-{idx + 1}", "name": name, "host_count": count}
        for idx, (name, count) in enumerate(
            sorted(counts.items(), key=lambda item: item[0])
        )
    ]
    return {"count": len(rows), "groups": rows}


@netai_tool(name="zabbix_get_hosts_in_group")  # type: ignore[operator]
def get_hosts_in_group(
    group: Annotated[str, "Group name (full or partial)"],
    limit: Annotated[int, "Maximum hosts to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    group_lc = normalize(group)
    matches = [
        host_brief(host)
        for host in FAKE_HOSTS.values()
        if group_lc in {normalize(item) for item in host["groups"]}
    ]
    if not matches:
        return {"error": f"group_not_found:{group}"}

    return {
        "group": {"groupid": f"g-{group_lc}", "name": group},
        "count": len(matches),
        "hosts": matches[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_problems")  # type: ignore[operator]
def get_problems(
    hostname_or_ip: Annotated[
        str | None, "Optional hostname/IP to scope problems"
    ] = None,
    group: Annotated[str | None, "Optional host-group filter"] = None,
    min_severity: Annotated[
        str | None, "Optional minimum severity"
    ] = DEFAULT_MIN_SEVERITY,
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    unacknowledged_only: Annotated[bool, "If true, only unacknowledged"] = False,
    unsuppressed_only: Annotated[bool, "If true, exclude suppressed"] = True,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip) if hostname_or_ip else None
    if hostname_or_ip and not host:
        return host_not_found(hostname_or_ip, "get_problems")

    rows = collect_problems(
        hostname_or_ip=hostname_or_ip,
        group=group,
        min_severity=min_severity,
        hours=hours,
        unacknowledged_only=unacknowledged_only,
        unsuppressed_only=unsuppressed_only,
        active_only=True,
    )
    return {
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "hostname_or_ip": hostname_or_ip,
            "group": group,
            "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "unacknowledged_only": unacknowledged_only,
            "unsuppressed_only": unsuppressed_only,
            "active_only": True,
        },
        "problems": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_recent_problems")  # type: ignore[operator]
def get_recent_problems(
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    min_severity: Annotated[
        str | None, "Optional minimum severity"
    ] = DEFAULT_MIN_SEVERITY,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    rows = collect_problems(
        min_severity=min_severity,
        hours=hours,
        unacknowledged_only=False,
        unsuppressed_only=True,
        active_only=False,
    )
    return {
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "active_only": False,
        },
        "problems": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_host_problems")  # type: ignore[operator]
def get_host_problems(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    min_severity: Annotated[
        str | None, "Optional minimum severity"
    ] = DEFAULT_MIN_SEVERITY,
    unacknowledged_only: Annotated[bool, "If true, only unacknowledged"] = False,
    unsuppressed_only: Annotated[bool, "If true, exclude suppressed"] = True,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_host_problems")

    rows = collect_problems(
        hostname_or_ip=hostname_or_ip,
        min_severity=min_severity,
        hours=hours,
        unacknowledged_only=unacknowledged_only,
        unsuppressed_only=unsuppressed_only,
        active_only=False,
    )
    return {
        "hostname_or_ip": hostname_or_ip,
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "unacknowledged_only": unacknowledged_only,
            "unsuppressed_only": unsuppressed_only,
            "active_only": False,
        },
        "problems": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_trigger_problems")  # type: ignore[operator]
def get_trigger_problems(
    trigger: Annotated[str, "Trigger ID or text match against trigger description"],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    located = lookup_trigger(trigger)
    if not located:
        return {"error": f"trigger_not_found:{trigger}"}
    host, trigger_row = located

    rows = [
        build_problem_row(host, problem)
        for problem in host["problems"]
        if problem["triggerid"] == trigger_row["triggerid"]
        and parse_iso(problem["since"]) >= hours_ago(hours)
    ]
    rows.sort(key=lambda row: parse_iso(str(row["since"])), reverse=True)

    return {
        "trigger": trigger_row,
        "count": len(rows[: clamp_limit(limit)]),
        "hours": hours if hours is not None else DEFAULT_HOURS,
        "problems": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_triggers")  # type: ignore[operator]
def get_triggers(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    min_severity: Annotated[
        str | None, "Optional minimum severity"
    ] = DEFAULT_MIN_SEVERITY,
    include_disabled: Annotated[bool, "If true, include disabled triggers"] = False,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_triggers")

    threshold = severity_threshold(min_severity)
    rows = []
    for trigger in host["triggers"]:
        if SEVERITY_ORDER.get(normalize(trigger["severity"]), 0) < threshold:
            continue
        if not include_disabled and not trigger["enabled"]:
            continue
        rows.append(trigger)

    rows.sort(
        key=lambda row: (
            SEVERITY_ORDER.get(normalize(str(row["severity"])), 0),
            parse_iso(str(row["last_change"])),
        ),
        reverse=True,
    )

    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
            "include_disabled": include_disabled,
        },
        "triggers": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_trigger_details")  # type: ignore[operator]
def get_trigger_details(
    trigger_id: Annotated[str, "Trigger ID"],
) -> dict[str, Any]:
    for host in FAKE_HOSTS.values():
        for trigger in host["triggers"]:
            if trigger["triggerid"] == str(trigger_id):
                return {
                    **trigger,
                    "hosts": [
                        {
                            "hostid": host["hostid"],
                            "hostname": host["hostname"],
                            "display_name": host["display_name"],
                        }
                    ],
                    "items": [
                        {
                            "itemid": metric_entry["itemid"],
                            "name": metric_entry["name"],
                            "key": metric_entry["key"],
                            "value_type": metric_entry["value_type"],
                        }
                        for metric_entry in host["metrics"][:3]
                    ],
                }
    return {"error": f"trigger_not_found:{trigger_id}"}


@netai_tool(name="zabbix_get_latest_metrics_data")  # type: ignore[operator]
def get_latest_metrics_data(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    key_patterns: Annotated[
        list[str] | None,
        "Optional item key patterns (supports contains or glob)",
    ] = None,
    limit: Annotated[int, "Maximum metrics to return"] = 200,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_latest_metrics_data")

    rows = collect_metrics(host, key_patterns)
    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {"key_patterns": key_patterns or []},
        "metrics": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_metrics_history")  # type: ignore[operator]
def get_metrics_history(
    item_id: Annotated[str | None, "Optional item ID"] = None,
    item_key: Annotated[str | None, "Optional item key"] = None,
    hostname_or_ip: Annotated[
        str | None,
        "Required with item_key when item_id is not provided.",
    ] = None,
    hours: Annotated[int | float | None, "Lookback window in hours"] = 6,
    aggregation: Annotated[str, "Aggregation mode: raw/avg/min/max"] = "raw",
    limit: Annotated[int, "Maximum points to return"] = 500,
) -> dict[str, Any]:
    if not item_id and not item_key:
        return {"error": "item_id_or_item_key_required"}

    selected_host: dict[str, Any] | None = None
    selected_metric: dict[str, Any] | None = None

    if item_id:
        for host in FAKE_HOSTS.values():
            for metric_entry in host["metrics"]:
                if metric_entry["itemid"] == str(item_id):
                    selected_host = host
                    selected_metric = metric_entry
                    break
            if selected_metric:
                break
    else:
        if not hostname_or_ip:
            return {"error": "hostname_or_ip_required_with_item_key"}
        selected_host = resolve_host(hostname_or_ip)
        if not selected_host:
            return host_not_found(hostname_or_ip, "get_metrics_history")
        for metric_entry in selected_host["metrics"]:
            if metric_entry["key"] == str(item_key):
                selected_metric = metric_entry
                break

    if not selected_metric:
        return {"error": f"item_not_found:{item_id or item_key}"}

    since_dt = hours_ago(hours)
    raw_points = [
        point
        for point in selected_metric["history"]
        if parse_iso(point["clock"]) >= since_dt
    ]
    raw_points.sort(key=lambda row: parse_iso(str(row["clock"])), reverse=True)

    aggregation_lc = normalize(aggregation) or "raw"
    points: list[dict[str, Any]]
    if aggregation_lc == "raw":
        points = raw_points[: clamp_limit(limit)]
    elif aggregation_lc in {"avg", "min", "max"}:
        if selected_metric["value_type"] not in {"0", "3"}:
            return {
                "error": "aggregation_requires_numeric_item",
                "value_type": selected_metric["value_type"],
            }
        numeric_values = [float(point["value"]) for point in raw_points]
        if not numeric_values:
            points = []
        else:
            value = {
                "avg": sum(numeric_values) / len(numeric_values),
                "min": min(numeric_values),
                "max": max(numeric_values),
            }[aggregation_lc]
            points = [
                {
                    "clock": raw_points[0]["clock"],
                    "value": round(value, 6),
                    "samples": len(numeric_values),
                }
            ]
    else:
        return {"error": f"invalid_aggregation:{aggregation}"}

    return {
        "item": {
            "itemid": selected_metric["itemid"],
            "name": selected_metric["name"],
            "key": selected_metric["key"],
            "unit": selected_metric["units"],
            "value_type": selected_metric["value_type"],
        },
        "aggregation": aggregation_lc,
        "hours": hours,
        "count": len(points),
        "points": points,
    }


@netai_tool(name="zabbix_get_host_metrics_summary")  # type: ignore[operator]
def get_host_metrics_summary(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    key_patterns: Annotated[
        list[str] | None,
        "Optional metric key patterns for summary focus",
    ] = None,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_host_metrics_summary")

    rows = collect_metrics(host, key_patterns)
    utilization = []
    error_items = []
    for row in rows:
        if "%" in str(row["unit"]):
            try:
                utilization.append({**row, "value": float(row["value"])})
            except (TypeError, ValueError):
                pass
        if not row["enabled"] or str(row["state"]) != "0":
            error_items.append(
                {
                    "itemid": row["itemid"],
                    "name": row["name"],
                    "key": row["key"],
                    "state": row["state"],
                    "enabled": row["enabled"],
                    "error": row["error"],
                }
            )

    utilization.sort(key=lambda item: float(item["value"]), reverse=True)

    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "inspected_metric_count": len(rows),
        "top_utilized_resources": utilization[:5],
        "error_items": error_items,
        "summary": {
            "top_utilized_count": min(len(utilization), 5),
            "error_item_count": len(error_items),
        },
    }


@netai_tool(name="zabbix_get_events")  # type: ignore[operator]
def get_events(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP to scope events.",
    ] = None,
    problem_event_id: Annotated[
        str | None,
        "Optional problem event ID to fetch surrounding trigger events.",
    ] = None,
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    include_ok_events: Annotated[
        bool,
        "If true, include OK/recovery events alongside problem events.",
    ] = True,
    limit: Annotated[int, "Maximum events to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if hostname_or_ip and not resolve_host(hostname_or_ip):
        return host_not_found(hostname_or_ip, "get_events")

    rows = collect_events(
        hostname_or_ip=hostname_or_ip,
        problem_event_id=problem_event_id,
        hours=hours,
        include_ok_events=include_ok_events,
    )

    if problem_event_id:
        has_problem_ref = any(
            row["eventid"] == problem_event_id or row["objectid"] == problem_event_id
            for row in rows
        )
        if not has_problem_ref:
            known_eventids = {
                problem["eventid"]
                for host in FAKE_HOSTS.values()
                for problem in host["problems"]
            }
            if problem_event_id not in known_eventids:
                return {"error": f"event_not_found:{problem_event_id}"}

    return {
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "hostname_or_ip": hostname_or_ip,
            "problem_event_id": problem_event_id,
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "include_ok_events": include_ok_events,
        },
        "events": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_audit_log")  # type: ignore[operator]
def get_audit_log(
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    actor: Annotated[str | None, "Optional actor/username filter"] = None,
    action: Annotated[str | None, "Optional action filter"] = None,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    actor_lc = normalize(actor)
    action_lc = normalize(action)
    since_dt = hours_ago(hours)

    rows = [
        row
        for row in AUDIT_LOG
        if parse_iso(row["clock"]) >= since_dt
        and (not actor_lc or actor_lc in normalize(row["actor"]))
        and (not action_lc or action_lc in normalize(row["action"]))
    ]
    rows.sort(key=lambda row: parse_iso(row["clock"]), reverse=True)

    return {
        "count": len(rows[: clamp_limit(limit)]),
        "filters": {
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "actor": actor,
            "action": action,
        },
        "entries": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_host_templates")  # type: ignore[operator]
def get_host_templates(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "get_host_templates")

    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "count": len(host["templates"]),
        "templates": host["templates"],
    }


@netai_tool(name="zabbix_get_maintenance")  # type: ignore[operator]
def get_maintenance(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP. If omitted, returns active maintenance windows.",
    ] = None,
) -> dict[str, Any]:
    host: dict[str, Any] | None = None
    if hostname_or_ip:
        host = resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(hostname_or_ip, "get_maintenance")

    entries: list[dict[str, Any]] = []
    for window in MAINTENANCE_WINDOWS:
        if host and host["hostid"] not in set(window["hosts"]):
            continue
        attached_hosts = [
            {
                "hostid": item["hostid"],
                "hostname": item["hostname"],
                "display_name": item["display_name"],
            }
            for item in FAKE_HOSTS.values()
            if item["hostid"] in set(window["hosts"])
        ]
        entries.append(
            {
                "maintenanceid": window["maintenanceid"],
                "name": window["name"],
                "active_since": window["active_since"],
                "active_till": window["active_till"],
                "description": window["description"],
                "maintenance_type": window["maintenance_type"],
                "hosts": attached_hosts,
                "tags": window["tags"],
            }
        )

    return {
        "hostname_or_ip": hostname_or_ip,
        "host_status": summarize_status(host) if host else None,
        "count": len(entries),
        "maintenance": entries,
    }


@netai_tool(name="zabbix_get_proxies")  # type: ignore[operator]
def get_proxies(
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        {
            "proxyid": proxy["proxyid"],
            "name": proxy["name"],
            "status": proxy["status"],
            "last_seen": proxy["last_seen"],
            "version": proxy["version"],
            "compatibility": proxy["compatibility"],
            "host_count": len(proxy["hostids"]),
        }
        for proxy in PROXIES
    ]
    rows.sort(key=lambda row: str(row["name"]))
    return {
        "count": len(rows[: clamp_limit(limit)]),
        "proxies": rows[: clamp_limit(limit)],
    }


@netai_tool(name="zabbix_get_zabbix_server_status")  # type: ignore[operator]
def get_zabbix_server_status() -> dict[str, Any]:
    hosts = list(FAKE_HOSTS.values())
    active_problems = len(
        [
            problem
            for host in hosts
            for problem in host["problems"]
            if problem["status"] == "active"
        ]
    )
    return {
        "api_version": "7.0.2-mock",
        "timestamp": NOW.isoformat(),
        "inventory": {
            "total_hosts": len(hosts),
            "enabled_hosts": len([host for host in hosts if host["status"] != "down"]),
            "proxy_count": len(PROXIES),
        },
        "alerts": {
            "active_problem_count": active_problems,
        },
        "queue": {"status": "mocked"},
        "performance": {"status": "api_reachable"},
    }


@netai_tool(name="zabbix_diagnose_host")  # type: ignore[operator]
def diagnose_host(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
) -> dict[str, Any]:
    host = resolve_host(hostname_or_ip)
    if not host:
        return host_not_found(hostname_or_ip, "diagnose_host")

    problems = collect_problems(
        hostname_or_ip=hostname_or_ip,
        min_severity=DEFAULT_MIN_SEVERITY,
        hours=hours,
        unacknowledged_only=False,
        unsuppressed_only=True,
        active_only=False,
    )[:20]
    events = collect_events(
        hostname_or_ip=hostname_or_ip,
        hours=hours,
        include_ok_events=True,
    )[:20]
    metrics = collect_metrics(host, ["*cpu*", "*memory*", "*icmp*", "*if*"])[:30]

    interface_rows = host["interfaces"]
    unhealthy_interfaces = [
        iface
        for iface in interface_rows
        if iface["oper_status"] != "up" or iface["error"]
    ]

    summary = (
        f"Host {host['hostname']} is {summarize_status(host)}; "
        f"{len(problems)} recent problems in the last {int(hours or DEFAULT_HOURS)}h; "
        f"{len(unhealthy_interfaces)} interface(s) are down or erroring."
    )

    return {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "hours": hours if hours is not None else DEFAULT_HOURS,
        "status": summarize_status(host),
        "problems": problems,
        "interfaces": interface_rows,
        "latest_metrics": metrics,
        "recent_events": events,
        "summary": summary,
    }


@netai_tool(name="zabbix_get_dashboard_snapshot")  # type: ignore[operator]
def get_dashboard_snapshot(
    dashboard: Annotated[
        str | None,
        "Dashboard slice: problems/hosts/overview.",
    ] = "problems",
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    limit: Annotated[int, "Maximum rows to return"] = 20,
) -> dict[str, Any]:
    dashboard_lc = normalize(dashboard) or "problems"

    if dashboard_lc == "problems":
        problems = collect_problems(
            min_severity=DEFAULT_MIN_SEVERITY,
            hours=hours,
            unacknowledged_only=False,
            unsuppressed_only=True,
            active_only=False,
        )
        return {
            "dashboard": "problems",
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "count": len(problems[: clamp_limit(limit)]),
            "data": problems[: clamp_limit(limit)],
        }

    if dashboard_lc == "hosts":
        hosts = [host_brief(host) for host in FAKE_HOSTS.values()]
        hosts.sort(key=lambda row: row["hostname"])
        return {
            "dashboard": "hosts",
            "count": len(hosts[: clamp_limit(limit)]),
            "data": hosts[: clamp_limit(limit)],
        }

    if dashboard_lc == "overview":
        hosts = list(FAKE_HOSTS.values())
        active_problems = collect_problems(
            min_severity=DEFAULT_MIN_SEVERITY,
            hours=hours,
            unacknowledged_only=False,
            unsuppressed_only=True,
            active_only=True,
        )
        return {
            "dashboard": "overview",
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "data": {
                "host_total": len(hosts),
                "up_hosts": len(
                    [host for host in hosts if summarize_status(host) == "up"]
                ),
                "down_hosts": len(
                    [host for host in hosts if summarize_status(host) == "down"]
                ),
                "maintenance_hosts": len(
                    [host for host in hosts if summarize_status(host) == "maintenance"]
                ),
                "active_problem_total": len(active_problems),
            },
        }

    return {
        "error": f"unknown_dashboard:{dashboard}",
        "available_dashboards": ["problems", "hosts", "overview"],
    }
