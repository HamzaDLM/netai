from typing import Annotated, Any

from haystack.tools import tool


_FAKE_DEVICES: dict[str, dict[str, Any]] = {
    "par-core-rtr-01": {
        "hostname": "par-core-rtr-01",
        "mgmt_ip": "10.10.100.1",
        "loopback_ip": "172.16.10.1",
        "site": "Paris-DC1",
        "role": "core-router",
        "vendor": "Juniper",
        "platform": "MX480",
        "status": "up",
    },
    "par-core-rtr-02": {
        "hostname": "par-core-rtr-02",
        "mgmt_ip": "10.10.100.2",
        "loopback_ip": "172.16.10.2",
        "site": "Paris-DC1",
        "role": "core-router",
        "vendor": "Juniper",
        "platform": "MX480",
        "status": "up",
    },
    "par-spine-01": {
        "hostname": "par-spine-01",
        "mgmt_ip": "10.10.110.1",
        "loopback_ip": "172.16.11.1",
        "site": "Paris-DC1",
        "role": "spine",
        "vendor": "Arista",
        "platform": "7280R3",
        "status": "up",
    },
    "par-spine-02": {
        "hostname": "par-spine-02",
        "mgmt_ip": "10.10.110.2",
        "loopback_ip": "172.16.11.2",
        "site": "Paris-DC1",
        "role": "spine",
        "vendor": "Arista",
        "platform": "7280R3",
        "status": "up",
    },
    "par-leaf-01": {
        "hostname": "par-leaf-01",
        "mgmt_ip": "10.10.120.1",
        "loopback_ip": "172.16.12.1",
        "site": "Paris-DC1",
        "role": "leaf",
        "vendor": "Arista",
        "platform": "7050X4",
        "status": "up",
    },
    "par-leaf-02": {
        "hostname": "par-leaf-02",
        "mgmt_ip": "10.10.120.2",
        "loopback_ip": "172.16.12.2",
        "site": "Paris-DC1",
        "role": "leaf",
        "vendor": "Arista",
        "platform": "7050X4",
        "status": "degraded",
    },
    "edge-fw-par-01": {
        "hostname": "edge-fw-par-01",
        "mgmt_ip": "10.10.1.1",
        "loopback_ip": "172.16.13.1",
        "site": "Paris-DC1",
        "role": "edge-firewall",
        "vendor": "Fortinet",
        "platform": "FortiGate 200F",
        "status": "up",
    },
    "edge-fw-par-02": {
        "hostname": "edge-fw-par-02",
        "mgmt_ip": "10.10.1.2",
        "loopback_ip": "172.16.13.2",
        "site": "Paris-DC1",
        "role": "edge-firewall",
        "vendor": "Fortinet",
        "platform": "FortiGate 200F",
        "status": "down",
    },
    "dist-rtr-nyc-01": {
        "hostname": "dist-rtr-nyc-01",
        "mgmt_ip": "10.20.1.1",
        "loopback_ip": "172.20.10.1",
        "site": "NYC-DC1",
        "role": "distribution-router",
        "vendor": "Juniper",
        "platform": "MX204",
        "status": "up",
    },
    "dist-rtr-nyc-02": {
        "hostname": "dist-rtr-nyc-02",
        "mgmt_ip": "10.20.1.2",
        "loopback_ip": "172.20.10.2",
        "site": "NYC-DC1",
        "role": "distribution-router",
        "vendor": "Juniper",
        "platform": "MX204",
        "status": "up",
    },
    "vpn-gw-lon-01": {
        "hostname": "vpn-gw-lon-01",
        "mgmt_ip": "10.40.1.5",
        "loopback_ip": "172.40.10.1",
        "site": "LON-DC1",
        "role": "vpn-gateway",
        "vendor": "Palo Alto",
        "platform": "PA-3220",
        "status": "down",
    },
    "vpn-gw-lon-02": {
        "hostname": "vpn-gw-lon-02",
        "mgmt_ip": "10.40.1.6",
        "loopback_ip": "172.40.10.2",
        "site": "LON-DC1",
        "role": "vpn-gateway",
        "vendor": "Palo Alto",
        "platform": "PA-3220",
        "status": "up",
    },
    "core-sw-sfo-01": {
        "hostname": "core-sw-sfo-01",
        "mgmt_ip": "10.30.1.11",
        "loopback_ip": "172.30.10.1",
        "site": "SFO-Campus",
        "role": "core-switch",
        "vendor": "Cisco",
        "platform": "Catalyst 9500-40X",
        "status": "up",
    },
    "core-sw-sfo-02": {
        "hostname": "core-sw-sfo-02",
        "mgmt_ip": "10.30.1.12",
        "loopback_ip": "172.30.10.2",
        "site": "SFO-Campus",
        "role": "core-switch",
        "vendor": "Cisco",
        "platform": "Catalyst 9500-40X",
        "status": "up",
    },
    "wlc-sfo-01": {
        "hostname": "wlc-sfo-01",
        "mgmt_ip": "10.30.1.20",
        "loopback_ip": "172.30.20.1",
        "site": "SFO-Campus",
        "role": "wireless-controller",
        "vendor": "Aruba",
        "platform": "Aruba 7210",
        "status": "maintenance",
    },
}

_FAKE_LINKS: list[dict[str, Any]] = [
    {
        "link_id": "lnk-001",
        "a_device": "par-core-rtr-01",
        "a_interface": "xe-0/0/0",
        "b_device": "par-core-rtr-02",
        "b_interface": "xe-0/0/0",
        "status": "up",
        "bandwidth_mbps": 100000,
        "metric": 10,
        "last_change": "2026-03-18T09:12:00Z",
    },
    {
        "link_id": "lnk-002",
        "a_device": "par-core-rtr-01",
        "a_interface": "xe-0/0/1",
        "b_device": "par-spine-01",
        "b_interface": "Ethernet1",
        "status": "up",
        "bandwidth_mbps": 100000,
        "metric": 15,
        "last_change": "2026-03-18T09:12:00Z",
    },
    {
        "link_id": "lnk-003",
        "a_device": "par-core-rtr-01",
        "a_interface": "xe-0/0/2",
        "b_device": "par-spine-02",
        "b_interface": "Ethernet1",
        "status": "up",
        "bandwidth_mbps": 100000,
        "metric": 15,
        "last_change": "2026-03-18T09:12:00Z",
    },
    {
        "link_id": "lnk-004",
        "a_device": "par-core-rtr-02",
        "a_interface": "xe-0/0/1",
        "b_device": "par-spine-01",
        "b_interface": "Ethernet2",
        "status": "up",
        "bandwidth_mbps": 100000,
        "metric": 15,
        "last_change": "2026-03-18T09:12:00Z",
    },
    {
        "link_id": "lnk-005",
        "a_device": "par-core-rtr-02",
        "a_interface": "xe-0/0/2",
        "b_device": "par-spine-02",
        "b_interface": "Ethernet2",
        "status": "up",
        "bandwidth_mbps": 100000,
        "metric": 15,
        "last_change": "2026-03-18T09:12:00Z",
    },
    {
        "link_id": "lnk-006",
        "a_device": "par-spine-01",
        "a_interface": "Ethernet10",
        "b_device": "par-leaf-01",
        "b_interface": "Ethernet49",
        "status": "up",
        "bandwidth_mbps": 40000,
        "metric": 20,
        "last_change": "2026-03-21T14:55:00Z",
    },
    {
        "link_id": "lnk-007",
        "a_device": "par-spine-01",
        "a_interface": "Ethernet11",
        "b_device": "par-leaf-02",
        "b_interface": "Ethernet49",
        "status": "degraded",
        "bandwidth_mbps": 40000,
        "metric": 20,
        "last_change": "2026-03-24T07:31:00Z",
    },
    {
        "link_id": "lnk-008",
        "a_device": "par-spine-02",
        "a_interface": "Ethernet10",
        "b_device": "par-leaf-01",
        "b_interface": "Ethernet50",
        "status": "up",
        "bandwidth_mbps": 40000,
        "metric": 20,
        "last_change": "2026-03-21T14:55:00Z",
    },
    {
        "link_id": "lnk-009",
        "a_device": "par-spine-02",
        "a_interface": "Ethernet11",
        "b_device": "par-leaf-02",
        "b_interface": "Ethernet50",
        "status": "up",
        "bandwidth_mbps": 40000,
        "metric": 20,
        "last_change": "2026-03-21T14:55:00Z",
    },
    {
        "link_id": "lnk-010",
        "a_device": "par-leaf-01",
        "a_interface": "Ethernet1",
        "b_device": "edge-fw-par-01",
        "b_interface": "port1",
        "status": "up",
        "bandwidth_mbps": 10000,
        "metric": 25,
        "last_change": "2026-03-22T11:18:00Z",
    },
    {
        "link_id": "lnk-011",
        "a_device": "par-leaf-02",
        "a_interface": "Ethernet1",
        "b_device": "edge-fw-par-02",
        "b_interface": "port1",
        "status": "down",
        "bandwidth_mbps": 10000,
        "metric": 25,
        "last_change": "2026-03-22T11:18:00Z",
    },
    {
        "link_id": "lnk-012",
        "a_device": "edge-fw-par-01",
        "a_interface": "wan1",
        "b_device": "dist-rtr-nyc-01",
        "b_interface": "xe-0/0/0",
        "status": "up",
        "bandwidth_mbps": 10000,
        "metric": 35,
        "last_change": "2026-03-23T19:04:00Z",
    },
    {
        "link_id": "lnk-013",
        "a_device": "edge-fw-par-02",
        "a_interface": "wan1",
        "b_device": "dist-rtr-nyc-02",
        "b_interface": "xe-0/0/0",
        "status": "down",
        "bandwidth_mbps": 10000,
        "metric": 35,
        "last_change": "2026-03-23T19:04:00Z",
    },
    {
        "link_id": "lnk-014",
        "a_device": "dist-rtr-nyc-01",
        "a_interface": "xe-0/0/1",
        "b_device": "dist-rtr-nyc-02",
        "b_interface": "xe-0/0/1",
        "status": "up",
        "bandwidth_mbps": 40000,
        "metric": 15,
        "last_change": "2026-03-20T05:20:00Z",
    },
    {
        "link_id": "lnk-015",
        "a_device": "dist-rtr-nyc-01",
        "a_interface": "xe-0/0/2",
        "b_device": "core-sw-sfo-01",
        "b_interface": "TenGig1/0/48",
        "status": "degraded",
        "bandwidth_mbps": 10000,
        "metric": 40,
        "last_change": "2026-03-24T06:02:00Z",
    },
    {
        "link_id": "lnk-016",
        "a_device": "dist-rtr-nyc-02",
        "a_interface": "xe-0/0/2",
        "b_device": "core-sw-sfo-02",
        "b_interface": "TenGig1/0/48",
        "status": "up",
        "bandwidth_mbps": 10000,
        "metric": 40,
        "last_change": "2026-03-20T05:20:00Z",
    },
    {
        "link_id": "lnk-017",
        "a_device": "core-sw-sfo-01",
        "a_interface": "Port-Channel10",
        "b_device": "core-sw-sfo-02",
        "b_interface": "Port-Channel10",
        "status": "up",
        "bandwidth_mbps": 40000,
        "metric": 10,
        "last_change": "2026-03-18T12:41:00Z",
    },
    {
        "link_id": "lnk-018",
        "a_device": "core-sw-sfo-01",
        "a_interface": "TenGig1/0/10",
        "b_device": "wlc-sfo-01",
        "b_interface": "uplink1",
        "status": "down",
        "bandwidth_mbps": 10000,
        "metric": 20,
        "last_change": "2026-03-24T04:11:00Z",
    },
    {
        "link_id": "lnk-019",
        "a_device": "core-sw-sfo-02",
        "a_interface": "TenGig1/0/10",
        "b_device": "wlc-sfo-01",
        "b_interface": "uplink2",
        "status": "maintenance",
        "bandwidth_mbps": 10000,
        "metric": 20,
        "last_change": "2026-03-24T04:12:00Z",
    },
    {
        "link_id": "lnk-020",
        "a_device": "dist-rtr-nyc-01",
        "a_interface": "ge-0/0/3",
        "b_device": "vpn-gw-lon-01",
        "b_interface": "ethernet1/1",
        "status": "down",
        "bandwidth_mbps": 1000,
        "metric": 45,
        "last_change": "2026-03-25T00:43:00Z",
    },
    {
        "link_id": "lnk-021",
        "a_device": "dist-rtr-nyc-02",
        "a_interface": "ge-0/0/3",
        "b_device": "vpn-gw-lon-02",
        "b_interface": "ethernet1/1",
        "status": "up",
        "bandwidth_mbps": 1000,
        "metric": 45,
        "last_change": "2026-03-21T10:14:00Z",
    },
    {
        "link_id": "lnk-022",
        "a_device": "vpn-gw-lon-01",
        "a_interface": "ha1",
        "b_device": "vpn-gw-lon-02",
        "b_interface": "ha1",
        "status": "up",
        "bandwidth_mbps": 1000,
        "metric": 5,
        "last_change": "2026-03-21T10:15:00Z",
    },
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_device(hostname_or_ip: str) -> dict[str, Any] | None:
    lookup = _normalize(hostname_or_ip)
    if not lookup:
        return None

    for device in _FAKE_DEVICES.values():
        if lookup in {_normalize(device["hostname"]), _normalize(device["mgmt_ip"])}:
            return device

    for device in _FAKE_DEVICES.values():
        haystack = f'{device["hostname"]} {device["mgmt_ip"]} {device["site"]} {device["role"]}'.lower()
        if lookup in haystack:
            return device
    return None


def _link_with_site(link: dict[str, Any]) -> dict[str, Any]:
    a_device = _FAKE_DEVICES[link["a_device"]]
    b_device = _FAKE_DEVICES[link["b_device"]]
    link_site = (
        a_device["site"]
        if a_device["site"] == b_device["site"]
        else f'{a_device["site"]}<->{b_device["site"]}'
    )
    return {**link, "site": link_site}


KNOWN_FAKE_DEVICES: list[dict[str, Any]] = [
    {
        "hostname": device["hostname"],
        "mgmt_ip": device["mgmt_ip"],
        "site": device["site"],
        "role": device["role"],
    }
    for device in _FAKE_DEVICES.values()
]


@tool(name="datamodel.get_known_devices")
def get_known_fake_devices() -> list[dict[str, Any]]:
    """Return the fake infra device catalog shared by datamodel tools."""
    return KNOWN_FAKE_DEVICES


@tool(name="datamodel.list_devices")
def list_devices(
    site: Annotated[str | None, "Optional site filter, e.g. Paris-DC1"] = None,
    role: Annotated[str | None, "Optional role filter, e.g. spine, core-router"] = None,
    status: Annotated[
        str | None, "Optional status filter, e.g. up/down/degraded"
    ] = None,
) -> dict[str, Any]:
    """List datamodel devices with optional site/role/status filters."""
    site_lc = _normalize(site)
    role_lc = _normalize(role)
    status_lc = _normalize(status)

    devices: list[dict[str, Any]] = []
    for device in _FAKE_DEVICES.values():
        if site_lc and _normalize(device["site"]) != site_lc:
            continue
        if role_lc and _normalize(device["role"]) != role_lc:
            continue
        if status_lc and _normalize(device["status"]) != status_lc:
            continue
        devices.append(device)
    return {"count": len(devices), "devices": devices}


@tool(name="datamodel.get_device")
def get_device(
    hostname_or_ip: Annotated[str, "Target device hostname or management IP"],
) -> dict[str, Any]:
    """Get one datamodel device with attached link counters."""
    device = _resolve_device(hostname_or_ip)
    if not device:
        return {
            "error": f"device_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }

    links = [
        link
        for link in _FAKE_LINKS
        if link["a_device"] == device["hostname"]
        or link["b_device"] == device["hostname"]
    ]
    status_counts: dict[str, int] = {}
    for link in links:
        key = _normalize(link["status"])
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        **device,
        "link_count": len(links),
        "link_status_counts": status_counts,
    }


@tool(name="datamodel.list_links")
def list_links(
    site: Annotated[
        str | None,
        "Optional site filter. Includes cross-site links if they contain the value.",
    ] = None,
    status: Annotated[
        str | None, "Optional status filter, e.g. up/down/degraded/maintenance"
    ] = None,
) -> dict[str, Any]:
    """List topology links with endpoint/interface and status data."""
    site_lc = _normalize(site)
    status_lc = _normalize(status)
    links: list[dict[str, Any]] = []

    for link in _FAKE_LINKS:
        materialized = _link_with_site(link)
        if site_lc and site_lc not in _normalize(materialized["site"]):
            continue
        if status_lc and _normalize(materialized["status"]) != status_lc:
            continue
        links.append(materialized)

    return {"count": len(links), "links": links}


@tool(name="datamodel.get_neighbors")
def get_neighbors(
    hostname_or_ip: Annotated[str, "Target device hostname or management IP"],
    only_up: Annotated[bool, "If true, include only links with status=up"] = False,
) -> dict[str, Any]:
    """Get immediate neighbors for one device, including per-link state."""
    device = _resolve_device(hostname_or_ip)
    if not device:
        return {
            "error": f"device_not_found:{hostname_or_ip}",
            "known_devices": KNOWN_FAKE_DEVICES,
        }

    neighbors: list[dict[str, Any]] = []
    for link in _FAKE_LINKS:
        if (
            link["a_device"] != device["hostname"]
            and link["b_device"] != device["hostname"]
        ):
            continue
        if only_up and _normalize(link["status"]) != "up":
            continue

        is_a_side = link["a_device"] == device["hostname"]
        peer_name = link["b_device"] if is_a_side else link["a_device"]
        peer_intf = link["b_interface"] if is_a_side else link["a_interface"]
        local_intf = link["a_interface"] if is_a_side else link["b_interface"]
        peer = _FAKE_DEVICES[peer_name]
        neighbors.append(
            {
                "link_id": link["link_id"],
                "local_interface": local_intf,
                "peer_hostname": peer["hostname"],
                "peer_mgmt_ip": peer["mgmt_ip"],
                "peer_interface": peer_intf,
                "peer_site": peer["site"],
                "peer_role": peer["role"],
                "status": link["status"],
                "bandwidth_mbps": link["bandwidth_mbps"],
                "last_change": link["last_change"],
            }
        )

    return {
        "hostname": device["hostname"],
        "mgmt_ip": device["mgmt_ip"],
        "neighbor_count": len(neighbors),
        "neighbors": neighbors,
    }


@tool(name="datamodel.get_topology")
def get_topology(
    site: Annotated[
        str | None,
        "Optional site scope (e.g. Paris-DC1). If omitted, returns full topology.",
    ] = None,
    include_only_link_statuses: Annotated[
        list[str] | None,
        "Optional link status filter list, e.g. ['up', 'degraded']",
    ] = None,
) -> dict[str, Any]:
    """Return graph-oriented topology payload (devices + links + status summary)."""
    site_lc = _normalize(site)
    allowed_statuses = {
        _normalize(s) for s in (include_only_link_statuses or []) if _normalize(s)
    }

    scoped_devices = list(_FAKE_DEVICES.values())
    if site_lc:
        scoped_devices = [
            device for device in scoped_devices if _normalize(device["site"]) == site_lc
        ]
    scoped_hostnames = {device["hostname"] for device in scoped_devices}

    scoped_links: list[dict[str, Any]] = []
    for link in _FAKE_LINKS:
        if site_lc and (
            link["a_device"] not in scoped_hostnames
            or link["b_device"] not in scoped_hostnames
        ):
            continue
        if allowed_statuses and _normalize(link["status"]) not in allowed_statuses:
            continue
        scoped_links.append(_link_with_site(link))

    status_counts: dict[str, int] = {}
    for link in scoped_links:
        key = _normalize(link["status"])
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "scope": site if site else "all_sites",
        "device_count": len(scoped_devices),
        "link_count": len(scoped_links),
        "link_status_counts": status_counts,
        "devices": scoped_devices,
        "links": scoped_links,
    }
