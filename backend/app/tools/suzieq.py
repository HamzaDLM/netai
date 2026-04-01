from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from haystack.tools import tool

from app.core.config import project_settings


SUZIEQ_API_VERSION = "v2"


class SuzieQToolError(RuntimeError):
    pass


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return normalize(value) in {"1", "true", "yes", "on"}


def suzieq_enabled() -> bool:
    env_value = os.getenv("SUZIEQ_ENABLED")
    if env_value is not None:
        return parse_bool_env(env_value, default=False)
    return bool(getattr(project_settings, "SUZIEQ_ENABLED", False))


def suzieq_api_url() -> str:
    return (
        os.getenv("SUZIEQ_API_URL")
        or str(getattr(project_settings, "SUZIEQ_API_URL", "") or "")
        or "https://localhost:8000"
    )


def suzieq_api_token() -> str:
    return (
        os.getenv("SUZIEQ_API_TOKEN")
        or str(getattr(project_settings, "SUZIEQ_API_TOKEN", "") or "")
    )


def suzieq_timeout_seconds() -> float:
    env_value = os.getenv("SUZIEQ_TIMEOUT_SECONDS")
    if env_value:
        try:
            return float(env_value)
        except ValueError:
            pass
    configured_timeout = getattr(project_settings, "SUZIEQ_TIMEOUT_SECONDS", None)
    if isinstance(configured_timeout, (int, float)):
        return float(configured_timeout)
    return 12.0


def suzieq_verify_tls() -> bool:
    env_value = os.getenv("SUZIEQ_VERIFY_TLS")
    if env_value is not None:
        return parse_bool_env(env_value, default=True)
    configured_value = getattr(project_settings, "SUZIEQ_VERIFY_TLS", None)
    if isinstance(configured_value, bool):
        return configured_value
    return False


class SuzieQClient:
    """Thin client for SuzieQ REST API v2.

    SuzieQ REST server docs indicate endpoint style:
    /api/v2/<table>/<verb>?access_token=<api_key>
    """

    def __init__(self) -> None:
        if not suzieq_enabled():
            raise SuzieQToolError("suzieq_disabled")

        base_url = suzieq_api_url().rstrip("/")
        if not base_url:
            raise SuzieQToolError("missing_suzieq_api_url")

        self.base_url = base_url
        self.api_token = suzieq_api_token()
        self.timeout_seconds = suzieq_timeout_seconds()
        self.verify_tls = suzieq_verify_tls()

    def _request(
        self,
        table: str,
        verb: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        query_params: dict[str, Any] = dict(params or {})
        if self.api_token:
            query_params["access_token"] = self.api_token

        endpoint = f"{self.base_url}/api/{SUZIEQ_API_VERSION}/{table}/{verb}"
        try:
            with httpx.Client(timeout=self.timeout_seconds, verify=self.verify_tls) as http_client:
                response = http_client.get(endpoint, params=query_params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise SuzieQToolError(f"suzieq_request_failed:{exc}") from exc
        except ValueError as exc:
            raise SuzieQToolError("suzieq_invalid_json_response") from exc

    def show(self, table: str, **params: Any) -> Any:
        return self._request(table=table, verb="show", params=params)

    def summarize(self, table: str, **params: Any) -> Any:
        return self._request(table=table, verb="summarize", params=params)

    def unique(self, table: str, **params: Any) -> Any:
        return self._request(table=table, verb="unique", params=params)

    def aver(self, table: str, **params: Any) -> Any:
        return self._request(table=table, verb="aver", params=params)


def error_payload(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


def client() -> SuzieQClient:
    return SuzieQClient()


@tool(name="suzieq.list_namespaces")
def list_namespaces() -> dict[str, Any]:
    """List known namespaces from SuzieQ inventory data."""
    try:
        suzieq_client = client()
        response = suzieq_client.unique("device", columns="namespace")
        return {"namespaces": response}
    except Exception as exc:
        return error_payload("list_namespaces", exc)


@tool(name="suzieq.get_devices")
def get_devices(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    """Get device inventory and operational state."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        response = suzieq_client.show("device", **params)
        return {"devices": response}
    except Exception as exc:
        return error_payload("get_devices", exc)


@tool(name="suzieq.get_interfaces")
def get_interfaces(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ifname: Annotated[str | None, "Optional interface name filter"] = None,
    state: Annotated[str | None, "Optional state filter, e.g. up/down/notConnected"] = None,
) -> dict[str, Any]:
    """Get interface state, addresses, speed, and counters."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if ifname:
            params["ifname"] = ifname
        if state:
            params["state"] = state
        response = suzieq_client.show("interface", **params)
        return {"interfaces": response}
    except Exception as exc:
        return error_payload("get_interfaces", exc)


@tool(name="suzieq.get_lldp_neighbors")
def get_lldp_neighbors(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    """Get LLDP adjacency for topology visibility."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        response = suzieq_client.show("lldp", **params)
        return {"lldp_neighbors": response}
    except Exception as exc:
        return error_payload("get_lldp_neighbors", exc)


@tool(name="suzieq.get_bgp_sessions")
def get_bgp_sessions(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[str | None, "Optional BGP state filter (Established, NotEstd, etc.)"] = None,
) -> dict[str, Any]:
    """Get BGP session health, neighbors, and state."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if state:
            params["state"] = state
        response = suzieq_client.show("bgp", **params)
        return {"bgp_sessions": response}
    except Exception as exc:
        return error_payload("get_bgp_sessions", exc)


@tool(name="suzieq.get_ospf_neighbors")
def get_ospf_neighbors(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[str | None, "Optional OSPF state filter"] = None,
) -> dict[str, Any]:
    """Get OSPF adjacency and state details."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if state:
            params["state"] = state
        response = suzieq_client.show("ospf", **params)
        return {"ospf_neighbors": response}
    except Exception as exc:
        return error_payload("get_ospf_neighbors", exc)


@tool(name="suzieq.get_routes")
def get_routes(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    prefix: Annotated[str | None, "Optional route prefix filter"] = None,
    vrf: Annotated[str | None, "Optional VRF filter"] = None,
) -> dict[str, Any]:
    """Get routing table entries and next-hop information."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if prefix:
            params["prefix"] = prefix
        if vrf:
            params["vrf"] = vrf
        response = suzieq_client.show("route", **params)
        return {"routes": response}
    except Exception as exc:
        return error_payload("get_routes", exc)


@tool(name="suzieq.get_arp_nd")
def get_arp_nd(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ip_address: Annotated[str | None, "Optional ARP/ND IP filter"] = None,
) -> dict[str, Any]:
    """Get ARP/ND resolution table for endpoint visibility."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if ip_address:
            params["ipAddress"] = ip_address
        response = suzieq_client.show("arpnd", **params)
        return {"arp_nd": response}
    except Exception as exc:
        return error_payload("get_arp_nd", exc)


@tool(name="suzieq.get_mac_table")
def get_mac_table(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    vlan: Annotated[str | None, "Optional VLAN filter"] = None,
    macaddr: Annotated[str | None, "Optional MAC address filter"] = None,
) -> dict[str, Any]:
    """Get MAC forwarding table for L2 visibility."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if vlan:
            params["vlan"] = vlan
        if macaddr:
            params["macaddr"] = macaddr
        response = suzieq_client.show("mac", **params)
        return {"mac_table": response}
    except Exception as exc:
        return error_payload("get_mac_table", exc)


@tool(name="suzieq.get_path")
def get_path(
    namespace: Annotated[str, "Namespace to run path analysis in"],
    source: Annotated[str, "Source IP address or hostname"],
    destination: Annotated[str, "Destination IP address or hostname"],
    vrf: Annotated[str | None, "Optional VRF"] = None,
) -> dict[str, Any]:
    """Compute path between source and destination using SuzieQ path table."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {
            "namespace": namespace,
            "src": source,
            "dest": destination,
        }
        if vrf:
            params["vrf"] = vrf
        response = suzieq_client.show("path", **params)
        return {"path": response}
    except Exception as exc:
        return error_payload("get_path", exc)


@tool(name="suzieq.infrastructure_summary")
def infrastructure_summary(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    """High-level multi-domain summary to give LLM broad infra vision."""
    try:
        suzieq_client = client()
        common_params: dict[str, Any] = {}
        if namespace:
            common_params["namespace"] = namespace

        summary: dict[str, Any] = {"scope": namespace or "all_namespaces"}
        summary["devices"] = suzieq_client.summarize("device", **common_params)
        summary["interfaces"] = suzieq_client.summarize("interface", **common_params)
        summary["lldp"] = suzieq_client.summarize("lldp", **common_params)
        summary["bgp"] = suzieq_client.summarize("bgp", **common_params)
        summary["ospf"] = suzieq_client.summarize("ospf", **common_params)
        summary["routes"] = suzieq_client.summarize("route", **common_params)
        summary["arpnd"] = suzieq_client.summarize("arpnd", **common_params)
        summary["mac"] = suzieq_client.summarize("mac", **common_params)
        return summary
    except Exception as exc:
        return error_payload("infrastructure_summary", exc)


@tool(name="suzieq.check_control_plane_health")
def check_control_plane_health(
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    """Run SuzieQ assert checks relevant to protocol/control-plane health."""
    try:
        suzieq_client = client()
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace

        checks: dict[str, Any] = {"scope": namespace or "all_namespaces"}
        checks["bgp_assert"] = suzieq_client.aver("bgp", **params)
        checks["ospf_assert"] = suzieq_client.aver("ospf", **params)
        checks["interface_assert"] = suzieq_client.aver("interface", **params)
        return checks
    except Exception as exc:
        return error_payload("check_control_plane_health", exc)
