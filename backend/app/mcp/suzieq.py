"""Lazy, failure-isolated SuzieQ MCP tools for the internal NetAI agent."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider

_RELEVANT_TERMS = (
    "suzieq",
    "suzie q",
    "network state",
    "control plane",
    "control-plane",
    "bgp session",
    "ospf neighbor",
    "lldp neighbor",
    "route table",
    "routing table",
    "mac table",
    "arp table",
    "path analysis",
)


class SuzieQToolProvider(OptionalMCPToolProvider):
    """Discover read-only SuzieQ tools only for relevant requests."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        retry_after_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            config,
            connector="suzieq",
            display_name="SuzieQ",
            relevant_terms=_RELEVANT_TERMS,
            retry_after_seconds=retry_after_seconds,
        )
