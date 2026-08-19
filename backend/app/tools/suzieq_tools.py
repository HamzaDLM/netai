import asyncio
from typing import Annotated, Any

from haystack.components.agents import State

from app.core.config import project_settings
from app.infrastructure import InfrastructureClients, clients_from_state
from app.tools import netai_tool

SUZIEQ_API_VERSION = "v2"


class SuzieQToolError(RuntimeError):
    pass


class SuzieQClient:
    """Thin client for SuzieQ REST API v2.

    SuzieQ REST server docs indicate endpoint style:
    /api/v2/<table>/<verb>?access_token=<api_key>
    """

    def __init__(self, clients: InfrastructureClients) -> None:
        if not project_settings.SUZIEQ_ENABLED:
            raise SuzieQToolError("suzieq_disabled")

        base_url = project_settings.SUZIEQ_API_URL.rstrip("/")
        if not base_url:
            raise SuzieQToolError("missing_suzieq_api_url")

        self.base_url = base_url
        self.api_token = project_settings.SUZIEQ_API_TOKEN
        self.timeout_seconds = project_settings.SUZIEQ_TIMEOUT_SECONDS
        self.verify_tls = project_settings.SUZIEQ_VERIFY_TLS
        self.clients = clients

    async def _request(
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
            response = await self.clients.request(
                "suzieq",
                "GET",
                endpoint,
                params=query_params,
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise SuzieQToolError(f"suzieq_request_failed:{exc}") from exc

    async def show(self, table: str, **params: Any) -> Any:
        return await self._request(table=table, verb="show", params=params)

    async def summarize(self, table: str, **params: Any) -> Any:
        return await self._request(table=table, verb="summarize", params=params)

    async def unique(self, table: str, **params: Any) -> Any:
        return await self._request(table=table, verb="unique", params=params)

    async def aver(self, table: str, **params: Any) -> Any:
        return await self._request(table=table, verb="aver", params=params)


def error_payload(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


def client(agent_state: State) -> SuzieQClient:
    return SuzieQClient(clients_from_state(agent_state))


@netai_tool(name="suzieq_list_namespaces")  # type: ignore[operator]
async def list_namespaces(agent_state: State) -> dict[str, Any]:
    """List known namespaces from SuzieQ inventory data."""
    try:
        suzieq_client = client(agent_state)
        response = await suzieq_client.unique("device", columns="namespace")
        return {"namespaces": response}
    except Exception as exc:
        return error_payload("list_namespaces", exc)


@netai_tool(name="suzieq_get_devices")  # type: ignore[operator]
async def get_devices(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    """Get device inventory and operational state."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        response = await suzieq_client.show("device", **params)
        return {"devices": response}
    except Exception as exc:
        return error_payload("get_devices", exc)


@netai_tool(name="suzieq_get_interfaces")  # type: ignore[operator]
async def get_interfaces(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ifname: Annotated[str | None, "Optional interface name filter"] = None,
    state: Annotated[
        str | None, "Optional state filter, e.g. up/down/notConnected"
    ] = None,
) -> dict[str, Any]:
    """Get interface state, addresses, speed, and counters."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if ifname:
            params["ifname"] = ifname
        if state:
            params["state"] = state
        response = await suzieq_client.show("interface", **params)
        return {"interfaces": response}
    except Exception as exc:
        return error_payload("get_interfaces", exc)


@netai_tool(name="suzieq_get_lldp_neighbors")  # type: ignore[operator]
async def get_lldp_neighbors(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
) -> dict[str, Any]:
    """Get LLDP adjacency for topology visibility."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        response = await suzieq_client.show("lldp", **params)
        return {"lldp_neighbors": response}
    except Exception as exc:
        return error_payload("get_lldp_neighbors", exc)


@netai_tool(name="suzieq_get_bgp_sessions")  # type: ignore[operator]
async def get_bgp_sessions(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[
        str | None, "Optional BGP state filter (Established, NotEstd, etc.)"
    ] = None,
) -> dict[str, Any]:
    """Get BGP session health, neighbors, and state."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if state:
            params["state"] = state
        response = await suzieq_client.show("bgp", **params)
        return {"bgp_sessions": response}
    except Exception as exc:
        return error_payload("get_bgp_sessions", exc)


@netai_tool(name="suzieq_get_ospf_neighbors")  # type: ignore[operator]
async def get_ospf_neighbors(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    state: Annotated[str | None, "Optional OSPF state filter"] = None,
) -> dict[str, Any]:
    """Get OSPF adjacency and state details."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if state:
            params["state"] = state
        response = await suzieq_client.show("ospf", **params)
        return {"ospf_neighbors": response}
    except Exception as exc:
        return error_payload("get_ospf_neighbors", exc)


@netai_tool(name="suzieq_get_routes")  # type: ignore[operator]
async def get_routes(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    prefix: Annotated[str | None, "Optional route prefix filter"] = None,
    vrf: Annotated[str | None, "Optional VRF filter"] = None,
) -> dict[str, Any]:
    """Get routing table entries and next-hop information."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if prefix:
            params["prefix"] = prefix
        if vrf:
            params["vrf"] = vrf
        response = await suzieq_client.show("route", **params)
        return {"routes": response}
    except Exception as exc:
        return error_payload("get_routes", exc)


@netai_tool(name="suzieq_get_arp_nd")  # type: ignore[operator]
async def get_arp_nd(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    ip_address: Annotated[str | None, "Optional ARP/ND IP filter"] = None,
) -> dict[str, Any]:
    """Get ARP/ND resolution table for endpoint visibility."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if ip_address:
            params["ipAddress"] = ip_address
        response = await suzieq_client.show("arpnd", **params)
        return {"arp_nd": response}
    except Exception as exc:
        return error_payload("get_arp_nd", exc)


@netai_tool(name="suzieq_get_mac_table")  # type: ignore[operator]
async def get_mac_table(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
    hostname: Annotated[str | None, "Optional hostname filter"] = None,
    vlan: Annotated[str | None, "Optional VLAN filter"] = None,
    macaddr: Annotated[str | None, "Optional MAC address filter"] = None,
) -> dict[str, Any]:
    """Get MAC forwarding table for L2 visibility."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace
        if hostname:
            params["hostname"] = hostname
        if vlan:
            params["vlan"] = vlan
        if macaddr:
            params["macaddr"] = macaddr
        response = await suzieq_client.show("mac", **params)
        return {"mac_table": response}
    except Exception as exc:
        return error_payload("get_mac_table", exc)


@netai_tool(name="suzieq_get_path")  # type: ignore[operator]
async def get_path(
    agent_state: State,
    namespace: Annotated[str, "Namespace to run path analysis in"],
    source: Annotated[str, "Source IP address or hostname"],
    destination: Annotated[str, "Destination IP address or hostname"],
    vrf: Annotated[str | None, "Optional VRF"] = None,
) -> dict[str, Any]:
    """Compute path between source and destination using SuzieQ path table."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {
            "namespace": namespace,
            "src": source,
            "dest": destination,
        }
        if vrf:
            params["vrf"] = vrf
        response = await suzieq_client.show("path", **params)
        return {"path": response}
    except Exception as exc:
        return error_payload("get_path", exc)


@netai_tool(name="suzieq_infrastructure_summary")  # type: ignore[operator]
async def infrastructure_summary(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    """High-level multi-domain summary to give LLM broad infra vision."""
    try:
        suzieq_client = client(agent_state)
        common_params: dict[str, Any] = {}
        if namespace:
            common_params["namespace"] = namespace

        tables = ("device", "interface", "lldp", "bgp", "ospf", "route", "arpnd", "mac")
        values = await asyncio.gather(
            *(suzieq_client.summarize(table, **common_params) for table in tables)
        )
        keys = (
            "devices",
            "interfaces",
            "lldp",
            "bgp",
            "ospf",
            "routes",
            "arpnd",
            "mac",
        )
        summary: dict[str, Any] = {
            "scope": namespace or "all_namespaces",
            **dict(zip(keys, values, strict=True)),
        }
        return summary
    except Exception as exc:
        return error_payload("infrastructure_summary", exc)


@netai_tool(name="suzieq_check_control_plane_health")  # type: ignore[operator]
async def check_control_plane_health(
    agent_state: State,
    namespace: Annotated[str | None, "Optional namespace filter"] = None,
) -> dict[str, Any]:
    """Run SuzieQ assert checks relevant to protocol/control-plane health."""
    try:
        suzieq_client = client(agent_state)
        params: dict[str, Any] = {}
        if namespace:
            params["namespace"] = namespace

        bgp, ospf, interface = await asyncio.gather(
            suzieq_client.aver("bgp", **params),
            suzieq_client.aver("ospf", **params),
            suzieq_client.aver("interface", **params),
        )
        checks: dict[str, Any] = {
            "scope": namespace or "all_namespaces",
            "bgp_assert": bgp,
            "ospf_assert": ospf,
            "interface_assert": interface,
        }
        return checks
    except Exception as exc:
        return error_payload("check_control_plane_health", exc)
