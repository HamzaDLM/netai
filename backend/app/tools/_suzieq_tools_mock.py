from typing import Annotated, Any

from haystack.tools import tool

_FAKE_DEVICES: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "address": "10.10.100.1",
        "vendor": "juniper",
        "model": "mx480",
        "status": "alive",
    },
    {
        "namespace": "prod-paris",
        "hostname": "par-spine-01",
        "address": "10.10.110.1",
        "vendor": "arista",
        "model": "7280R3",
        "status": "alive",
    },
    {
        "namespace": "prod-nyc",
        "hostname": "dist-rtr-nyc-01",
        "address": "10.20.1.1",
        "vendor": "juniper",
        "model": "mx204",
        "status": "alive",
    },
]

_FAKE_INTERFACES: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "ifname": "xe-0/0/0",
        "state": "up",
        "adminState": "up",
    },
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "ifname": "xe-0/0/1",
        "state": "up",
        "adminState": "up",
    },
    {
        "namespace": "prod-nyc",
        "hostname": "dist-rtr-nyc-01",
        "ifname": "xe-0/0/2",
        "state": "down",
        "adminState": "up",
    },
]

_FAKE_LLDP: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "ifname": "xe-0/0/0",
        "peerHostname": "par-spine-01",
        "peerIfname": "Ethernet1",
    }
]

_FAKE_BGP: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "peer": "172.16.11.1",
        "asn": 65010,
        "state": "Established",
    },
    {
        "namespace": "prod-nyc",
        "hostname": "dist-rtr-nyc-01",
        "peer": "172.20.10.2",
        "asn": 65020,
        "state": "NotEstd",
    },
]

_FAKE_OSPF: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "ifname": "xe-0/0/1",
        "adjState": "full",
    }
]

_FAKE_ROUTES: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "prefix": "10.30.0.0/16",
        "nexthopIps": ["172.16.11.1"],
        "vrf": "default",
    }
]

_FAKE_ARPND: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-core-rtr-01",
        "ipAddress": "10.10.100.10",
        "macaddr": "aa:bb:cc:dd:ee:01",
    }
]

_FAKE_MAC: list[dict[str, Any]] = [
    {
        "namespace": "prod-paris",
        "hostname": "par-spine-01",
        "vlan": "100",
        "macaddr": "aa:bb:cc:dd:ee:01",
        "oif": "Ethernet10",
    }
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _filter(rows: list[dict[str, Any]], **filters: str | None) -> list[dict[str, Any]]:
    out = rows
    for key, raw_value in filters.items():
        if not raw_value:
            continue
        target = _normalize(raw_value)
        out = [row for row in out if _normalize(str(row.get(key, ""))) == target]
    return out


@tool(name="suzieq.list_namespaces")  # type: ignore[operator]
def list_namespaces() -> dict[str, Any]:
    namespaces = sorted({str(device["namespace"]) for device in _FAKE_DEVICES})
    return {"namespaces": namespaces}


@tool(name="suzieq.get_devices")  # type: ignore[operator]
def get_devices(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    return {"devices": _filter(_FAKE_DEVICES, namespace=namespace, hostname=hostname)}


@tool(name="suzieq.get_interfaces")  # type: ignore[operator]
def get_interfaces(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ifname: Annotated[str | None, "Optional interface name filter"] = None,
    state: Annotated[str | None, "Optional state filter"] = None,
) -> dict[str, Any]:
    return {
        "interfaces": _filter(
            _FAKE_INTERFACES,
            namespace=namespace,
            hostname=hostname,
            ifname=ifname,
            state=state,
        )
    }


@tool(name="suzieq.get_lldp_neighbors")  # type: ignore[operator]
def get_lldp_neighbors(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    return {
        "lldp_neighbors": _filter(_FAKE_LLDP, namespace=namespace, hostname=hostname)
    }


@tool(name="suzieq.get_bgp_sessions")  # type: ignore[operator]
def get_bgp_sessions(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[str | None, "Optional BGP state filter"] = None,
) -> dict[str, Any]:
    return {
        "bgp_sessions": _filter(
            _FAKE_BGP, namespace=namespace, hostname=hostname, state=state
        )
    }


@tool(name="suzieq.get_ospf_neighbors")  # type: ignore[operator]
def get_ospf_neighbors(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[str | None, "Optional OSPF state filter"] = None,
) -> dict[str, Any]:
    rows = _filter(_FAKE_OSPF, namespace=namespace, hostname=hostname)
    if state:
        rows = [
            row
            for row in rows
            if _normalize(str(row.get("adjState"))) == _normalize(state)
        ]
    return {"ospf_neighbors": rows}


@tool(name="suzieq.get_routes")  # type: ignore[operator]
def get_routes(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    prefix: Annotated[str | None, "Optional route prefix filter"] = None,
    vrf: Annotated[str | None, "Optional VRF filter"] = None,
) -> dict[str, Any]:
    return {
        "routes": _filter(
            _FAKE_ROUTES, namespace=namespace, hostname=hostname, prefix=prefix, vrf=vrf
        )
    }


@tool(name="suzieq.get_arp_nd")  # type: ignore[operator]
def get_arp_nd(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ip_address: Annotated[str | None, "Optional ARP/ND IP filter"] = None,
) -> dict[str, Any]:
    return {
        "arp_nd": _filter(
            _FAKE_ARPND, namespace=namespace, hostname=hostname, ipAddress=ip_address
        )
    }


@tool(name="suzieq.get_mac_table")  # type: ignore[operator]
def get_mac_table(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    vlan: Annotated[str | None, "Optional VLAN filter"] = None,
    macaddr: Annotated[str | None, "Optional MAC address filter"] = None,
) -> dict[str, Any]:
    return {
        "mac_table": _filter(
            _FAKE_MAC,
            namespace=namespace,
            hostname=hostname,
            vlan=vlan,
            macaddr=macaddr,
        )
    }


@tool(name="suzieq.get_path")  # type: ignore[operator]
def get_path(
    namespace: Annotated[str, "Namespace to run path analysis in"],
    source: Annotated[str, "Source IP address or hostname"],
    destination: Annotated[str, "Destination IP address or hostname"],
    vrf: Annotated[str | None, "Optional VRF"] = None,
) -> dict[str, Any]:
    return {
        "path": [
            {
                "namespace": namespace,
                "src": source,
                "dest": destination,
                "vrf": vrf or "default",
                "hops": ["par-core-rtr-01", "par-spine-01", "dist-rtr-nyc-01"],
                "reachable": True,
            }
        ]
    }


@tool(name="suzieq.infrastructure_summary")  # type: ignore[operator]
def infrastructure_summary(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    devices = _filter(_FAKE_DEVICES, namespace=namespace)
    interfaces = _filter(_FAKE_INTERFACES, namespace=namespace)
    bgp = _filter(_FAKE_BGP, namespace=namespace)
    return {
        "scope": namespace or "all_namespaces",
        "devices": {"count": len(devices)},
        "interfaces": {"count": len(interfaces)},
        "bgp": {
            "count": len(bgp),
            "not_established": len(
                [
                    row
                    for row in bgp
                    if _normalize(str(row.get("state"))) != "established"
                ]
            ),
        },
        "lldp": {"count": len(_filter(_FAKE_LLDP, namespace=namespace))},
        "ospf": {"count": len(_filter(_FAKE_OSPF, namespace=namespace))},
        "routes": {"count": len(_filter(_FAKE_ROUTES, namespace=namespace))},
        "arpnd": {"count": len(_filter(_FAKE_ARPND, namespace=namespace))},
        "mac": {"count": len(_filter(_FAKE_MAC, namespace=namespace))},
    }


@tool(name="suzieq.check_control_plane_health")  # type: ignore[operator]
def check_control_plane_health(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    bgp = _filter(_FAKE_BGP, namespace=namespace)
    bad_bgp = [row for row in bgp if _normalize(str(row.get("state"))) != "established"]
    down_interfaces = [
        row
        for row in _filter(_FAKE_INTERFACES, namespace=namespace)
        if _normalize(str(row.get("state"))) != "up"
    ]
    return {
        "scope": namespace or "all_namespaces",
        "bgp_assert": {
            "passed": len(bad_bgp) == 0,
            "failing_sessions": bad_bgp,
        },
        "ospf_assert": {"passed": True, "failing_neighbors": []},
        "interface_assert": {
            "passed": len(down_interfaces) == 0,
            "down_interfaces": down_interfaces,
        },
    }
