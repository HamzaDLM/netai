"""Runtime registry for the tools available to the NetAI agent.

The registry is intentionally built from the actual Haystack ``Tool`` objects.
It is the single source of truth for the Agent, the connector catalogue, policy
checks, and the MCP server adapter.  Keeping those consumers on the same
objects avoids the former AST-based catalogue and the duplicate specialist
agent tool lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType

from haystack.tools import SearchableToolset, Tool, Toolset

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class Connector:
    key: str
    name: str
    description: str
    module: str


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        key="zabbix",
        name="Zabbix",
        description="Monitoring hosts, alerts, events, metrics, and availability.",
        module="app.tools.zabbix_tools",
    ),
    Connector(
        key="suzieq",
        name="SuzieQ",
        description="Live network state, routing, neighbors, paths, and control-plane health.",
        module="app.tools.suzieq_tools",
    ),
    Connector(
        key="bitbucket",
        name="Bitbucket",
        description="Versioned device configurations, diffs, commits, and change history.",
        module="app.tools.bitbucket_tools",
    ),
    Connector(
        key="servicenow",
        name="ServiceNow",
        description="Incidents, problems, changes, configuration items, and service context.",
        module="app.tools.servicenow_tools",
    ),
    Connector(
        key="datamodel",
        name="Topology model",
        description="Infrastructure inventory, links, neighbors, and graph topology.",
        module="app.tools.datamodel_tools",
    ),
    Connector(
        key="network",
        name="Network diagnostics",
        description="Safe reachability, path, and latency diagnostic visualizations.",
        module="app.tools.probe_tools",
    ),
)

_MOCK_MODULES: dict[str, str] = {
    "zabbix": "app.tools._zabbix_tools_mock",
    "suzieq": "app.tools._suzieq_tools_mock",
    "bitbucket": "app.tools._bitbucket_tools_mock",
    "servicenow": "app.tools._servicenow_tools_mock",
}


def _tools_in(module: ModuleType) -> list[Tool]:
    """Return the distinct Haystack tools declared by a module."""

    discovered: dict[str, Tool] = {}
    for value in vars(module).values():
        if isinstance(value, Tool):
            discovered.setdefault(value.name, value)
    return sorted(discovered.values(), key=lambda item: item.name)


def _humanize_tool_name(name: str, connector_key: str) -> str:
    prefix = f"{connector_key}_"
    concise_name = name.removeprefix(prefix)
    return concise_name.replace("_", " ").strip()


def _prefer_native_async(registered_tool: Tool) -> None:
    """Give pure in-memory tools a native async path without a worker thread."""

    if registered_tool.async_function is not None or registered_tool.function is None:
        return
    function = registered_tool.function

    async def invoke(**kwargs: object) -> object:
        return function(**kwargs)

    registered_tool.async_function = invoke


class AsyncSearchableToolset(SearchableToolset):
    """SearchableToolset whose small BM25 lookup runs natively on the event loop."""

    def _create_search_tool(self) -> Tool:
        search_tool = super()._create_search_tool()
        _prefer_native_async(search_tool)
        return search_tool


class ToolRegistry:
    """Own the local tool catalogue and its native searchable view."""

    def __init__(self, settings: Settings) -> None:
        self._connectors = CONNECTORS
        self._tools_by_connector: dict[str, list[Tool]] = {}
        self._tools_by_name: dict[str, Tool] = {}

        for connector in self._connectors:
            module_name = connector.module
            if settings.TOOLS_USE_MOCK_DATA:
                module_name = _MOCK_MODULES.get(connector.key, module_name)
            tools = _tools_in(import_module(module_name))
            for registered_tool in tools:
                if registered_tool.name in self._tools_by_name:
                    raise ValueError(
                        f"Duplicate NetAI tool name: {registered_tool.name}"
                    )

                summary = registered_tool.description.strip()
                if not summary:
                    summary = (
                        f"Read-only {connector.name} operation: "
                        f"{_humanize_tool_name(registered_tool.name, connector.key)}."
                    )
                if not summary.startswith(f"[{connector.name}]"):
                    summary = f"[{connector.name}] {summary}"
                registered_tool.description = summary
                setattr(registered_tool, "netai_connector", connector.key)
                setattr(
                    registered_tool,
                    "netai_effect",
                    self._effect_for(registered_tool),
                )
                if settings.TOOLS_USE_MOCK_DATA or connector.key in {
                    "datamodel",
                    "network",
                }:
                    _prefer_native_async(registered_tool)
                self._tools_by_name[registered_tool.name] = registered_tool

            self._tools_by_connector[connector.key] = tools

        self.searchable = self.searchable_with()

    def searchable_with(
        self,
        *extras: Toolset,
        exclude_connectors: set[str] | None = None,
    ) -> SearchableToolset:
        """Build a searchable view with request-scoped external toolsets."""

        excluded = exclude_connectors or set()
        catalog: list[Tool | Toolset] = [
            tool
            for tool in self.tools
            if getattr(tool, "netai_connector", None) not in excluded
        ]
        catalog.extend(extras)
        searchable = AsyncSearchableToolset(
            catalog=catalog,
            top_k=5,
            search_threshold=8,
            search_tool_description=(
                "Search NetAI's read-only infrastructure tool catalogue. Use connector, "
                "data source, and operation keywords; then call the returned tool directly."
            ),
            search_tool_parameters_description={
                "tool_keywords": (
                    "Connector and operation keywords, for example 'zabbix host problems', "
                    "'topology neighbors', or 'bitbucket config diff'."
                ),
                "k": "Maximum number of relevant tools to load.",
            },
        )
        searchable.warm_up()
        return searchable

    @staticmethod
    def _effect_for(registered_tool: Tool) -> str:
        presentation = getattr(registered_tool, "netai_presentation", None)
        if isinstance(presentation, dict):
            effect = presentation.get("effect")
            if isinstance(effect, str) and effect:
                return effect
        return "read_only"

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools_by_name.values())

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools_by_name)

    def get(self, name: str) -> Tool | None:
        return self._tools_by_name.get(name)

    def connector_for(self, name: str) -> str:
        if name == "search_tools":
            return "internal"
        registered_tool = self.get(name)
        if registered_tool is None:
            return "infrahub" if name.startswith("infrahub_") else "external"
        return str(getattr(registered_tool, "netai_connector", "local"))

    def effect_for(self, name: str) -> str:
        if name == "search_tools":
            return "internal"
        registered_tool = self.get(name)
        if registered_tool is None:
            return "read_only"
        return str(getattr(registered_tool, "netai_effect", "read_only"))

    def presentation_for(self, name: str) -> dict[str, object] | None:
        registered_tool = self.get(name)
        presentation = (
            getattr(registered_tool, "netai_presentation", None)
            if registered_tool is not None
            else None
        )
        return dict(presentation) if isinstance(presentation, dict) else None

    def catalog(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for connector in self._connectors:
            tools = self._tools_by_connector[connector.key]
            entries.append(
                {
                    "agent_key": connector.key,
                    "agent_name": connector.name,
                    "description": connector.description,
                    "specialist_tool": None,
                    "source": "local",
                    "dynamic_tools": True,
                    "connection_status": "not_applicable",
                    "status_message": "",
                    "mcp_config_name": None,
                    "tools": [
                        {
                            "python_name": registered_tool.name,
                            "runtime_name": registered_tool.name,
                            "summary": registered_tool.description,
                        }
                        for registered_tool in tools
                    ],
                }
            )
        return entries
