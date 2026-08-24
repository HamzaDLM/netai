"""Lazy, failure-isolated Infrahub MCP tools for the internal NetAI agent."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider

_RELEVANT_TERMS = (
    "infrahub",
    "source of truth",
    "source-of-truth",
    "intended state",
    "intent data",
)


class InfrahubToolProvider(OptionalMCPToolProvider):
    """Discover read-only Infrahub tools only for relevant requests."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        retry_after_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            config,
            connector="infrahub",
            display_name="Infrahub",
            relevant_terms=_RELEVANT_TERMS,
            retry_after_seconds=retry_after_seconds,
        )
