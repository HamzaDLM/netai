"""Connector catalogue derived from the runtime Haystack Tool registry."""

from __future__ import annotations

from haystack.tools import Toolset

from app.core.config import Settings, project_settings
from app.mcp.infrahub import InfrahubToolProvider
from app.mcp.logs import LogToolProvider
from app.mcp.suzieq import SuzieQToolProvider
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


def _suzieq_mcp_entry(
    *,
    status: str = "not_checked",
    status_message: str = "SuzieQ is connected only when it is needed.",
    tools: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "agent_key": "suzieq_mcp",
        "agent_name": "SuzieQ MCP",
        "description": (
            "Read-only live network state, routing, neighbors, paths, and "
            "control-plane health supplied by an external MCP server."
        ),
        "specialist_tool": None,
        "source": "mcp",
        "dynamic_tools": True,
        "connection_status": status,
        "status_message": status_message,
        "mcp_config_name": "suzieq_mcp",
        "tools": tools or [],
    }


def _logs_mcp_entry(
    *,
    status: str = "not_checked",
    status_message: str = "Log intelligence is connected only when it is needed.",
    tools: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "agent_key": "syslog",
        "agent_name": "Log intelligence",
        "description": (
            "Read-only bounded syslog events and structured severity, facility, "
            "and event-code summaries supplied by the standalone log service."
        ),
        "specialist_tool": None,
        "source": "mcp",
        "dynamic_tools": True,
        "connection_status": status,
        "status_message": status_message,
        "mcp_config_name": "log_mcp",
        "tools": tools or [],
    }


def get_agent_tool_catalog(
    registry: ToolRegistry | None = None,
    *,
    settings: Settings = project_settings,
) -> list[dict[str, object]]:
    """Return local tools plus descriptors for optional MCP connectors."""

    runtime_registry = registry or ToolRegistry(settings)
    return [
        *runtime_registry.catalog(),
        _infrahub_entry(),
        _suzieq_mcp_entry(),
        _logs_mcp_entry(),
    ]


def _remote_tools(
    toolset: Toolset | None,
    *,
    connector_name: str,
) -> list[dict[str, object]]:
    if toolset is None:
        return []
    return [
        {
            "python_name": remote_tool.name,
            "runtime_name": remote_tool.name,
            "summary": remote_tool.description
            or f"Read-only {connector_name} operation.",
        }
        for remote_tool in toolset.tools
    ]


async def get_resolved_agent_tool_catalog(
    *,
    registry: ToolRegistry,
    infrahub: InfrahubToolProvider,
    suzieq: SuzieQToolProvider,
    logs: LogToolProvider,
) -> list[dict[str, object]]:
    """Resolve optional MCP entries without affecting local connectors."""

    return [
        *registry.catalog(),
        _infrahub_entry(
            status=infrahub.status,
            status_message=infrahub.status_message,
            tools=_remote_tools(infrahub.toolset, connector_name="Infrahub"),
        ),
        _suzieq_mcp_entry(
            status=suzieq.status,
            status_message=suzieq.status_message,
            tools=_remote_tools(suzieq.toolset, connector_name="SuzieQ"),
        ),
        _logs_mcp_entry(
            status=logs.status,
            status_message=logs.status_message,
            tools=_remote_tools(logs.toolset, connector_name="Log intelligence"),
        ),
    ]
