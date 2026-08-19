"""Connector catalogue derived from the runtime Haystack Tool registry."""

from __future__ import annotations

from haystack_integrations.tools.mcp import MCPToolset

from app.core.config import Settings, project_settings
from app.mcp.infrahub import InfrahubToolProvider
from app.tools.registry import ToolRegistry


def _infrahub_entry(
    *,
    status: str = "not_checked",
    status_message: str = "Infrahub is connected only when it is needed.",
    tools: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "agent_key": "infrahub",
        "agent_name": "Infrahub",
        "description": (
            "Read-only infrastructure source-of-truth inventory, schemas, "
            "relationships, topology, and intended state."
        ),
        "specialist_tool": None,
        "source": "mcp",
        "dynamic_tools": True,
        "connection_status": status,
        "status_message": status_message,
        "mcp_config_name": "infrahub_mcp",
        "tools": tools or [],
    }


def get_agent_tool_catalog(
    registry: ToolRegistry | None = None,
    *,
    settings: Settings = project_settings,
) -> list[dict[str, object]]:
    """Return local runtime tools plus the lazy Infrahub connector descriptor."""

    runtime_registry = registry or ToolRegistry(settings)
    return [*runtime_registry.catalog(), _infrahub_entry()]


def _remote_tools(toolset: MCPToolset | None) -> list[dict[str, object]]:
    if toolset is None:
        return []
    return [
        {
            "python_name": remote_tool.name,
            "runtime_name": remote_tool.name,
            "summary": remote_tool.description or "Read-only Infrahub operation.",
        }
        for remote_tool in toolset.tools
    ]


async def get_resolved_agent_tool_catalog(
    *,
    registry: ToolRegistry,
    infrahub: InfrahubToolProvider,
) -> list[dict[str, object]]:
    """Resolve the optional MCP entry without affecting local connectors."""

    toolset = await infrahub.get_toolset(force=True)
    return [
        *registry.catalog(),
        _infrahub_entry(
            status=infrahub.status,
            status_message=infrahub.status_message,
            tools=_remote_tools(toolset),
        ),
    ]
