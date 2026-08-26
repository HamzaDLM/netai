"""Failure-isolated Infrahub MCP capabilities consumed by NetAI."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider

TOOL_GROUP_PROMPT = """
Infrahub is the infrastructure source of truth for intended inventory, schemas,
relationships, and topology. Inspect schema or object metadata before composing
queries when the data model is uncertain. Prefer targeted node/relationship queries
over broad graph retrieval, and reuse identifiers returned by earlier calls. Treat
Infrahub as intended or modeled state unless the returned data explicitly represents
observed state; compare it with SuzieQ, Zabbix, or logs before claiming current
operational behavior. Keep graph results scoped to the device or relationship under
investigation.
""".strip()


class InfrahubToolProvider(OptionalMCPToolProvider):
    """Name the generic consumed-MCP provider at the composition boundary."""

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
            tool_group_prompt=TOOL_GROUP_PROMPT,
            retry_after_seconds=retry_after_seconds,
        )
