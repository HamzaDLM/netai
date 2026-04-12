from typing import Annotated, Any

from haystack.tools import tool

_SEVERITY_ORDER = {
    "not_classified": 0,
    "information": 1,
    "warning": 2,
    "average": 3,
    "high": 4,
    "disaster": 5,
}


_FAKE_ZABBIX_HOSTS: dict[str, dict[str, Any]] = {
    "edge-fw-par-01": {
        "hostid": "10001",
        "hostname": "edge-fw-par-01",
        "display_name": "Paris Edge Firewall",
        "ip": "10.10.1.1",
        "site": "Paris-DC1",
        "vendor": "Fortinet",
        "model": "FortiGate 200F",
        "os": "FortiOS 7.0.13",
        "status": "up",
        "maintenance": False,
        "groups": ["Firewalls", "Edge", "Paris"],
        "tags": {"environment": "prod", "role": "edge-firewall", "tier": "critical"},
        "availability": {"agent": "available", "snmp": "available", "icmp": "up"},
        "interfaces": [
            {
                "name": "wan1",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "in_utilization_pct": 52.4,
                "out_utilization_pct": 47.1,
                "error_rate_pct": 0.02,
            },
            {
                "name": "lan-core",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 10000,
                "in_utilization_pct": 34.9,
                "out_utilization_pct": 38.6,
                "error_rate_pct": 0.01,
            },
        ],
        "metrics": {
            "cpu.util": {
                "value": 41.3,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "memory.util": {
                "value": 68.1,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.in[wan1]": {
                "value": 520.2,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.out[wan1]": {
                "value": 469.1,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "icmppingloss": {
                "value": 0.0,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
        },
        "problems": [
            {
                "eventid": "70011",
                "name": "VPN tunnel packet loss on branch-sfo",
                "severity": "warning",
                "status": "active",
                "since": "2026-03-17T19:21:00Z",
                "acknowledged": True,
            }
        ],
    },
    "core-sw-par-01": {
        "hostid": "10002",
        "hostname": "core-sw-par-01",
        "display_name": "Paris Core Switch 01",
        "ip": "10.10.1.11",
        "site": "Paris-DC1",
        "vendor": "Cisco",
        "model": "Catalyst 9500-40X",
        "os": "IOS-XE 17.12.04a",
        "status": "up",
        "maintenance": False,
        "groups": ["Switches", "Core", "Paris"],
        "tags": {"environment": "prod", "role": "core-switch", "tier": "critical"},
        "availability": {"agent": "available", "snmp": "available", "icmp": "up"},
        "interfaces": [
            {
                "name": "TenGig1/0/48",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 10000,
                "in_utilization_pct": 71.8,
                "out_utilization_pct": 66.2,
                "error_rate_pct": 0.00,
            },
            {
                "name": "Port-Channel10",
                "type": "lag",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 40000,
                "in_utilization_pct": 58.1,
                "out_utilization_pct": 55.0,
                "error_rate_pct": 0.00,
            },
        ],
        "metrics": {
            "cpu.util": {
                "value": 52.7,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "memory.util": {
                "value": 61.4,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "temperature": {
                "value": 43.2,
                "unit": "C",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.in[Port-Channel10]": {
                "value": 23100,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.out[Port-Channel10]": {
                "value": 21880,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
        },
        "problems": [],
    },
    "dist-rtr-nyc-01": {
        "hostid": "10003",
        "hostname": "dist-rtr-nyc-01",
        "display_name": "NYC Distribution Router 01",
        "ip": "10.20.1.1",
        "site": "NYC-DC1",
        "vendor": "Juniper",
        "model": "MX204",
        "os": "Junos 23.2R2",
        "status": "up",
        "maintenance": False,
        "groups": ["Routers", "Distribution", "NYC"],
        "tags": {"environment": "prod", "role": "distribution-router", "tier": "high"},
        "availability": {"agent": "unavailable", "snmp": "available", "icmp": "up"},
        "interfaces": [
            {
                "name": "xe-0/0/0",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 10000,
                "in_utilization_pct": 83.1,
                "out_utilization_pct": 79.9,
                "error_rate_pct": 0.03,
            },
            {
                "name": "ae2",
                "type": "lag",
                "admin_status": "up",
                "oper_status": "degraded",
                "speed_mbps": 20000,
                "in_utilization_pct": 91.2,
                "out_utilization_pct": 88.0,
                "error_rate_pct": 0.13,
            },
        ],
        "metrics": {
            "cpu.util": {
                "value": 76.4,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "memory.util": {
                "value": 73.8,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "bgp.peer.count.down": {
                "value": 1,
                "unit": "peers",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.in[ae2]": {
                "value": 18210,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.out[ae2]": {
                "value": 17605,
                "unit": "Mbps",
                "last_clock": "2026-03-17T20:55:00Z",
            },
        },
        "problems": [
            {
                "eventid": "70021",
                "name": "BGP peer flapping toward ISP-B",
                "severity": "average",
                "status": "active",
                "since": "2026-03-17T18:37:00Z",
                "acknowledged": False,
            }
        ],
    },
    "wlc-sfo-01": {
        "hostid": "10004",
        "hostname": "wlc-sfo-01",
        "display_name": "SFO Wireless Controller",
        "ip": "10.30.1.20",
        "site": "SFO-Campus",
        "vendor": "Aruba",
        "model": "Aruba 7210",
        "os": "ArubaOS 8.11.2.0",
        "status": "maintenance",
        "maintenance": True,
        "groups": ["Wireless", "Controllers", "SFO"],
        "tags": {
            "environment": "prod",
            "role": "wireless-controller",
            "tier": "medium",
        },
        "availability": {"agent": "unknown", "snmp": "unknown", "icmp": "down"},
        "interfaces": [
            {
                "name": "uplink1",
                "type": "physical",
                "admin_status": "down",
                "oper_status": "down",
                "speed_mbps": 1000,
                "in_utilization_pct": 0.0,
                "out_utilization_pct": 0.0,
                "error_rate_pct": 0.00,
            }
        ],
        "metrics": {
            "cpu.util": {
                "value": 0.0,
                "unit": "%",
                "last_clock": "2026-03-17T20:30:00Z",
            },
            "memory.util": {
                "value": 0.0,
                "unit": "%",
                "last_clock": "2026-03-17T20:30:00Z",
            },
            "ap.count.connected": {
                "value": 0,
                "unit": "APs",
                "last_clock": "2026-03-17T20:30:00Z",
            },
            "icmpping": {
                "value": 0,
                "unit": "bool",
                "last_clock": "2026-03-17T20:30:00Z",
            },
        },
        "problems": [
            {
                "eventid": "70031",
                "name": "Host unavailable by ICMP",
                "severity": "high",
                "status": "suppressed",
                "since": "2026-03-17T16:05:00Z",
                "acknowledged": True,
            }
        ],
    },
    "access-sw-sfo-24": {
        "hostid": "10005",
        "hostname": "access-sw-sfo-24",
        "display_name": "SFO Access Switch 24",
        "ip": "10.30.2.24",
        "site": "SFO-Campus",
        "vendor": "Cisco",
        "model": "Catalyst 9300-48P",
        "os": "IOS-XE 17.09.05",
        "status": "up",
        "maintenance": False,
        "groups": ["Switches", "Access", "SFO"],
        "tags": {"environment": "prod", "role": "access-switch", "tier": "medium"},
        "availability": {"agent": "available", "snmp": "available", "icmp": "up"},
        "interfaces": [
            {
                "name": "Gig1/0/1",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "up",
                "speed_mbps": 1000,
                "in_utilization_pct": 12.4,
                "out_utilization_pct": 9.1,
                "error_rate_pct": 0.00,
            },
            {
                "name": "Gig1/0/47",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "down",
                "speed_mbps": 1000,
                "in_utilization_pct": 0.0,
                "out_utilization_pct": 0.0,
                "error_rate_pct": 0.50,
            },
        ],
        "metrics": {
            "cpu.util": {
                "value": 23.8,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "memory.util": {
                "value": 49.2,
                "unit": "%",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "temperature": {
                "value": 38.9,
                "unit": "C",
                "last_clock": "2026-03-17T20:55:00Z",
            },
            "net.if.errors[Gig1/0/47]": {
                "value": 152,
                "unit": "errors",
                "last_clock": "2026-03-17T20:55:00Z",
            },
        },
        "problems": [
            {
                "eventid": "70041",
                "name": "Interface Gig1/0/47 link down",
                "severity": "warning",
                "status": "active",
                "since": "2026-03-17T14:11:00Z",
                "acknowledged": False,
            }
        ],
    },
    "vpn-gw-lon-01": {
        "hostid": "10006",
        "hostname": "vpn-gw-lon-01",
        "display_name": "London VPN Gateway 01",
        "ip": "10.40.1.5",
        "site": "LON-DC1",
        "vendor": "Palo Alto",
        "model": "PA-3220",
        "os": "PAN-OS 11.0.4",
        "status": "down",
        "maintenance": False,
        "groups": ["VPN", "Gateways", "London"],
        "tags": {"environment": "prod", "role": "vpn-gateway", "tier": "critical"},
        "availability": {"agent": "unavailable", "snmp": "unavailable", "icmp": "down"},
        "interfaces": [
            {
                "name": "ethernet1/1",
                "type": "physical",
                "admin_status": "up",
                "oper_status": "down",
                "speed_mbps": 1000,
                "in_utilization_pct": 0.0,
                "out_utilization_pct": 0.0,
                "error_rate_pct": 0.00,
            }
        ],
        "metrics": {
            "cpu.util": {
                "value": 0.0,
                "unit": "%",
                "last_clock": "2026-03-17T20:50:00Z",
            },
            "memory.util": {
                "value": 0.0,
                "unit": "%",
                "last_clock": "2026-03-17T20:50:00Z",
            },
            "icmpping": {
                "value": 0,
                "unit": "bool",
                "last_clock": "2026-03-17T20:50:00Z",
            },
            "vpn.tunnel.up": {
                "value": 0,
                "unit": "tunnels",
                "last_clock": "2026-03-17T20:50:00Z",
            },
        },
        "problems": [
            {
                "eventid": "70051",
                "name": "Host unreachable",
                "severity": "disaster",
                "status": "active",
                "since": "2026-03-17T20:12:00Z",
                "acknowledged": False,
            },
            {
                "eventid": "70052",
                "name": "All VPN tunnels down",
                "severity": "high",
                "status": "active",
                "since": "2026-03-17T20:13:00Z",
                "acknowledged": False,
            },
        ],
    },
}


def _host_brief(host: dict[str, Any]) -> dict[str, Any]:
    return {
        "hostid": host["hostid"],
        "hostname": host["hostname"],
        "display_name": host["display_name"],
        "ip": host["ip"],
        "site": host["site"],
        "status": host["status"],
        "maintenance": host["maintenance"],
        "groups": host["groups"],
        "tags": host["tags"],
    }


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_host(hostname_or_ip: str) -> dict[str, Any] | None:
    lookup = _normalize(hostname_or_ip)
    if not lookup:
        return None

    # Prefer exact matching first.
    for host in _FAKE_ZABBIX_HOSTS.values():
        if lookup in {_normalize(host["hostname"]), _normalize(host["ip"])}:
            return host

    # Then allow prefix/contains matches for convenience in tests.
    for host in _FAKE_ZABBIX_HOSTS.values():
        haystack = f"{host['hostname']} {host['display_name']} {host['ip']}".lower()
        if lookup in haystack:
            return host
    return None


def _severity_allowed(
    severity: str,
    min_severity: str | None,
) -> bool:
    if not min_severity:
        return True
    return _SEVERITY_ORDER.get(_normalize(severity), -1) >= _SEVERITY_ORDER.get(
        _normalize(min_severity), 0
    )


KNOWN_FAKE_DEVICES: list[dict[str, Any]] = [
    {"hostname": host["hostname"], "ip": host["ip"], "site": host["site"]}
    for host in _FAKE_ZABBIX_HOSTS.values()
]


@tool(name="zabbix.list_hosts")  # type: ignore[operator]
def list_zabbix_hosts(
    status: Annotated[str | None, "Optional status filter: up/down/maintenance"] = None,
    group: Annotated[
        str | None, "Optional group filter (example: Switches, Firewalls)"
    ] = None,
) -> dict[str, Any]:
    """List fake Zabbix hosts with optional status/group filters."""
    status_lc = _normalize(status)
    group_lc = _normalize(group)
    hosts = []
    for host in _FAKE_ZABBIX_HOSTS.values():
        if status_lc and _normalize(host["status"]) != status_lc:
            continue
        if group_lc and group_lc not in {_normalize(g) for g in host["groups"]}:
            continue
        hosts.append(_host_brief(host))
    return {"count": len(hosts), "hosts": hosts}


@tool(name="zabbix.get_known_devices")  # type: ignore[operator]
def get_known_fake_devices() -> list[dict[str, Any]]:
    """Return the shared fake device catalog used by all Zabbix tools."""
    return KNOWN_FAKE_DEVICES


@tool(name="zabbix.get_host_status")  # type: ignore[operator]
def get_host_status(
    hostname_or_ip: Annotated[
        str,
        "Target device hostname or IP, e.g. edge-fw-par-01 or 10.10.1.1",
    ],
) -> dict[str, Any]:
    """Get a host status summary including availability and active problem counts."""
    host = _resolve_host(hostname_or_ip)
    if not host:
        return {
            "error": f"host_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }

    active_problems = [p for p in host["problems"] if p["status"] == "active"]
    highest_severity = "information"
    if active_problems:
        highest_severity = max(
            active_problems,
            key=lambda p: _SEVERITY_ORDER.get(_normalize(p["severity"]), 0),
        )["severity"]

    return {
        **_host_brief(host),
        "availability": host["availability"],
        "active_problem_count": len(active_problems),
        "highest_active_severity": highest_severity,
    }


@tool(name="zabbix.get_host_inventory")  # type: ignore[operator]
def get_host_inventory(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Get static inventory information for a host."""
    host = _resolve_host(hostname_or_ip)
    if not host:
        return {
            "error": f"host_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }
    return {
        **_host_brief(host),
        "vendor": host["vendor"],
        "model": host["model"],
        "os": host["os"],
    }


@tool(name="zabbix.get_host_interfaces")  # type: ignore[operator]
def get_host_interfaces(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    only_problematic: Annotated[
        bool,
        "If true, return only interfaces that are down/degraded or have error_rate_pct > 0.1",
    ] = False,
) -> dict[str, Any]:
    """Return host interface status details."""
    host = _resolve_host(hostname_or_ip)
    if not host:
        return {
            "error": f"host_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }

    interfaces = host["interfaces"]
    if only_problematic:
        interfaces = [
            iface
            for iface in interfaces
            if iface["oper_status"] in {"down", "degraded"}
            or iface["error_rate_pct"] > 0.1
        ]
    return {"hostname": host["hostname"], "ip": host["ip"], "interfaces": interfaces}


@tool(name="zabbix.get_host_metrics")  # type: ignore[operator]
def get_host_metrics(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    metric_keys: Annotated[
        list[str] | None,
        "Optional metric keys to fetch. If omitted, returns all available metrics.",
    ] = None,
) -> dict[str, Any]:
    """Get latest fake metric values for a host."""
    host = _resolve_host(hostname_or_ip)
    if not host:
        return {
            "error": f"host_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }

    metrics = host["metrics"]
    if metric_keys:
        selected = {k: metrics[k] for k in metric_keys if k in metrics}
        missing = [k for k in metric_keys if k not in metrics]
        return {
            "hostname": host["hostname"],
            "ip": host["ip"],
            "metrics": selected,
            "missing_metric_keys": missing,
        }
    return {"hostname": host["hostname"], "ip": host["ip"], "metrics": metrics}


@tool(name="zabbix.get_trigger_events")  # type: ignore[operator]
def get_trigger_events(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP. If omitted, search across all hosts.",
    ] = None,
    only_active: Annotated[bool, "If true, include only active trigger events"] = True,
    min_severity: Annotated[
        str | None,
        "Optional minimum severity: information/warning/average/high/disaster",
    ] = None,
    limit: Annotated[int, "Maximum number of events to return"] = 20,
) -> dict[str, Any]:
    """Return fake trigger/problem events for one host or for all hosts."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    if hostname_or_ip:
        host = _resolve_host(hostname_or_ip)
        if not host:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": KNOWN_FAKE_DEVICES,
            }
        hosts = [host]
    else:
        hosts = list(_FAKE_ZABBIX_HOSTS.values())

    events: list[dict[str, Any]] = []
    for host in hosts:
        for event in host["problems"]:
            if only_active and event["status"] != "active":
                continue
            if not _severity_allowed(event["severity"], min_severity):
                continue
            events.append(
                {
                    "eventid": event["eventid"],
                    "hostname": host["hostname"],
                    "ip": host["ip"],
                    "name": event["name"],
                    "severity": event["severity"],
                    "status": event["status"],
                    "since": event["since"],
                    "acknowledged": event["acknowledged"],
                }
            )

    events.sort(key=lambda item: item["since"], reverse=True)
    return {"count": len(events[:limit]), "events": events[:limit]}


@tool(name="zabbix.get_problem_summary")  # type: ignore[operator]
def get_problem_summary(
    group: Annotated[str | None, "Optional group filter"] = None,
) -> dict[str, Any]:
    """Provide a high-level summary of active problems by severity and host."""
    group_lc = _normalize(group)
    hosts = list(_FAKE_ZABBIX_HOSTS.values())
    if group_lc:
        hosts = [
            host
            for host in hosts
            if group_lc in {_normalize(item) for item in host["groups"]}
        ]

    severity_totals = {key: 0 for key in _SEVERITY_ORDER if key != "not_classified"}
    host_totals: dict[str, int] = {}
    total_active = 0

    for host in hosts:
        active = [p for p in host["problems"] if p["status"] == "active"]
        if active:
            host_totals[host["hostname"]] = len(active)
        for event in active:
            sev = _normalize(event["severity"])
            if sev not in severity_totals:
                severity_totals[sev] = 0
            severity_totals[sev] += 1
            total_active += 1

    return {
        "scope": group if group else "all_hosts",
        "active_problem_total": total_active,
        "active_by_severity": severity_totals,
        "active_by_host": host_totals,
    }
