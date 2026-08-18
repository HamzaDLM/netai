import ast
import asyncio
import copy
import logging
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import project_settings
from app.mcp.mcp_client import (
    MCPClientConfig,
    NetAIMCPClient,
    get_mcp_client_config,
)

APP_DIR = Path(__file__).resolve().parent
AGENTS_DIR = APP_DIR / "agents"
logger = logging.getLogger(__name__)


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().splitlines()[0].strip()


def _resolve_call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_tool_names_from_list(node: ast.expr) -> list[str]:
    if not isinstance(node, ast.List):
        return []
    names: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Name):
            names.append(elt.id)
            continue
        if isinstance(elt, ast.Call):
            call_name = _resolve_call_name(elt.func)
            if call_name == "cast" and len(elt.args) >= 2:
                second = elt.args[1]
                if isinstance(second, ast.Name):
                    names.append(second.id)
                elif isinstance(second, ast.Call):
                    nested_name = _resolve_call_name(second.func)
                    if nested_name:
                        names.append(nested_name)
                continue
            inner_name = _resolve_call_name(elt.func)
            if inner_name:
                names.append(inner_name)
    return names


def _literal_string(node: ast.expr) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _extract_component_tool_metadata(
    module_node: ast.Module,
) -> tuple[str | None, str]:
    for node in module_node.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Call):
            continue
        component_tool_name = _resolve_call_name(value.func)
        if not component_tool_name or not component_tool_name.endswith("ComponentTool"):
            continue
        name: str | None = None
        description = ""
        for keyword in value.keywords:
            if keyword.arg == "name":
                name = _literal_string(keyword.value)
            elif keyword.arg == "description":
                description = _literal_string(keyword.value) or ""
        return name, description
    return None, ""


def _extract_mcp_config_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if _resolve_call_name(node.func) not in {
        "create_haystack_toolset",
        "discover_haystack_tools",
    }:
        return None

    config_node: ast.expr | None = node.args[0] if node.args else None
    for keyword in node.keywords:
        if keyword.arg == "config":
            config_node = keyword.value
            break
    return config_node.id if isinstance(config_node, ast.Name) else None


def _extract_import_map(module_node: ast.Module) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in module_node.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("app.tools"):
            continue
        for alias in node.names:
            imported_name = alias.asname or alias.name
            mapping[imported_name] = node.module
    return mapping


@lru_cache(maxsize=64)
def _load_tool_module_metadata(module_name: str) -> dict[str, dict[str, str | None]]:
    relative_path = Path(*module_name.split(".")).with_suffix(".py")
    module_path = APP_DIR.parent / relative_path
    if not module_path.exists():
        return {}

    module_node = ast.parse(module_path.read_text(encoding="utf-8"))
    metadata: dict[str, dict[str, str | None]] = {}

    for node in module_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        runtime_name: str | None = None
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            decorator_name = _resolve_call_name(decorator.func)
            if decorator_name not in {"netai_tool", "tool"}:
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        runtime_name = keyword.value.value
        metadata[node.name] = {
            "summary": _first_line(ast.get_docstring(node)),
            "runtime_name": runtime_name,
        }

    return metadata


@lru_cache(maxsize=1)
def get_agent_tool_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for path in sorted(AGENTS_DIR.glob("*_agent.py")):
        if path.name == "orchestrator_agent.py":
            continue

        module_node = ast.parse(path.read_text(encoding="utf-8"))
        imports_map = _extract_import_map(module_node)

        tools: list[str] = []
        source = "local"
        dynamic_tools = False
        mcp_config_name: str | None = None
        for node in module_node.body:
            value = None
            if isinstance(node, ast.Assign):
                if (
                    len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id.endswith("_tools")
                ):
                    value = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id.endswith(
                    "_tools"
                ):
                    value = node.value

            if value is None:
                continue
            mcp_config_name = _extract_mcp_config_name(value)
            if mcp_config_name is not None:
                source = "mcp"
                dynamic_tools = True
            else:
                tools = _extract_tool_names_from_list(value)
            break

        tool_entries: list[dict[str, str | None]] = []
        for tool_name in tools:
            module_name = imports_map.get(tool_name)
            module_meta = _load_tool_module_metadata(module_name) if module_name else {}
            tool_meta = module_meta.get(tool_name, {})
            tool_entries.append(
                {
                    "python_name": tool_name,
                    "runtime_name": tool_meta.get("runtime_name"),
                    "summary": tool_meta.get("summary") or "",
                }
            )

        agent_key = path.stem.replace("_agent", "")
        specialist_tool, description = _extract_component_tool_metadata(module_node)
        catalog.append(
            {
                "agent_key": agent_key,
                "agent_name": agent_key.replace("_", " ").title(),
                "description": description,
                "specialist_tool": specialist_tool,
                "source": source,
                "dynamic_tools": dynamic_tools,
                "connection_status": (
                    "not_checked" if source == "mcp" else "not_applicable"
                ),
                "status_message": (
                    "Remote tools are discovered when the connector catalogue is opened."
                    if source == "mcp"
                    else ""
                ),
                "mcp_config_name": mcp_config_name,
                "tools": tool_entries,
            }
        )

    return catalog


async def _discover_mcp_catalog_tools(config: MCPClientConfig) -> list[Any]:
    configured_timeout = max(
        0.1,
        project_settings.MCP_CATALOG_DISCOVERY_TIMEOUT_SECONDS,
    )
    discovery_config = replace(
        config,
        timeout=max(0.1, min(config.timeout, configured_timeout)),
    )
    async with NetAIMCPClient(
        discovery_config.url,
        token=discovery_config.token,
        headers=discovery_config.headers,
        timeout=discovery_config.timeout,
    ) as client:
        return await client.list_tools()


async def _resolve_catalog_entry(entry: dict[str, Any]) -> dict[str, Any]:
    resolved = copy.deepcopy(entry)
    if resolved.get("source") != "mcp":
        return resolved

    config_name = resolved.get("mcp_config_name")
    config = (
        get_mcp_client_config(config_name) if isinstance(config_name, str) else None
    )
    if config is None:
        resolved["connection_status"] = "not_configured"
        resolved["status_message"] = "No MCP client configuration was found."
        return resolved

    try:
        remote_tools = await _discover_mcp_catalog_tools(config)
    except Exception as exc:
        logger.info(
            "MCP catalogue discovery failed for agent %s: %s",
            resolved.get("agent_key", "unknown"),
            exc,
        )
        resolved["connection_status"] = "unavailable"
        resolved["status_message"] = (
            "The MCP server was unavailable during catalogue discovery."
        )
        return resolved

    resolved["tools"] = [
        {
            "python_name": tool.name,
            "runtime_name": tool.name,
            "summary": tool.description or "",
        }
        for tool in remote_tools
    ]
    resolved["connection_status"] = "available"
    resolved["status_message"] = "MCP tools were discovered successfully."
    return resolved


async def get_resolved_agent_tool_catalog() -> list[dict[str, Any]]:
    """Return the catalogue with MCP tools discovered concurrently and safely."""

    entries = get_agent_tool_catalog()
    return list(
        await asyncio.gather(*(_resolve_catalog_entry(item) for item in entries))
    )
