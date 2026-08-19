from types import SimpleNamespace
from typing import cast

import pytest

from app.core.config import project_settings
from app.skills_catalog import (
    get_agent_tool_catalog,
    get_resolved_agent_tool_catalog,
)
from app.tools.registry import ToolRegistry


def _entry(catalog: list[dict[str, object]], key: str) -> dict[str, object]:
    return next(item for item in catalog if item["agent_key"] == key)


def test_catalog_is_derived_from_runtime_registry() -> None:
    registry = ToolRegistry(project_settings)

    catalog = get_agent_tool_catalog(registry)

    zabbix = _entry(catalog, "zabbix")
    tools = cast(list[dict[str, object]], zabbix["tools"])
    runtime_names = {tool["runtime_name"] for tool in tools}
    assert runtime_names == {
        name for name in registry.tool_names if name.startswith("zabbix_")
    }
    infrahub = _entry(catalog, "infrahub")
    assert infrahub["source"] == "mcp"
    assert infrahub["connection_status"] == "not_checked"
    assert infrahub["specialist_tool"] is None


class FakeInfrahubProvider:
    status = "available"
    status_message = "connected"

    async def get_toolset(self, *, force: bool = False):
        assert force is True
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="infrahub_query_nodes",
                    description="Query Infrahub nodes without changing them.",
                )
            ]
        )


@pytest.mark.anyio
async def test_resolved_catalog_uses_lifecycle_mcp_provider() -> None:
    registry = ToolRegistry(project_settings)

    catalog = await get_resolved_agent_tool_catalog(
        registry=registry,
        infrahub=FakeInfrahubProvider(),  # type: ignore[arg-type]
    )

    infrahub = _entry(catalog, "infrahub")
    assert infrahub["connection_status"] == "available"
    assert infrahub["tools"] == [
        {
            "python_name": "infrahub_query_nodes",
            "runtime_name": "infrahub_query_nodes",
            "summary": "Query Infrahub nodes without changing them.",
        }
    ]
