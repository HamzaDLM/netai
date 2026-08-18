import asyncio
from types import SimpleNamespace
from typing import Any

from app import skills_catalog


def _infrahub_entry(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    return next(item for item in catalog if item["agent_key"] == "infrahub")


def test_static_catalog_detects_mcp_backed_agent() -> None:
    skills_catalog.get_agent_tool_catalog.cache_clear()

    entry = _infrahub_entry(skills_catalog.get_agent_tool_catalog())

    assert entry["source"] == "mcp"
    assert entry["dynamic_tools"] is True
    assert entry["mcp_config_name"] == "infrahub_mcp"
    assert entry["connection_status"] == "not_checked"
    assert entry["specialist_tool"] == "infrahub_specialist"
    assert "Read-only Infrahub" in entry["description"]
    assert entry["tools"] == []


def test_resolved_catalog_includes_discovered_mcp_tools(monkeypatch) -> None:
    async def fake_discovery(_config):
        return [
            SimpleNamespace(
                name="infrahub_query_nodes",
                description="Query Infrahub nodes without changing them.",
            )
        ]

    monkeypatch.setattr(
        skills_catalog,
        "_discover_mcp_catalog_tools",
        fake_discovery,
    )

    entry = _infrahub_entry(
        asyncio.run(skills_catalog.get_resolved_agent_tool_catalog())
    )

    assert entry["connection_status"] == "available"
    assert entry["tools"] == [
        {
            "python_name": "infrahub_query_nodes",
            "runtime_name": "infrahub_query_nodes",
            "summary": "Query Infrahub nodes without changing them.",
        }
    ]


def test_resolved_catalog_keeps_unavailable_mcp_agent(monkeypatch) -> None:
    async def failed_discovery(_config):
        raise OSError("server unavailable")

    monkeypatch.setattr(
        skills_catalog,
        "_discover_mcp_catalog_tools",
        failed_discovery,
    )

    entry = _infrahub_entry(
        asyncio.run(skills_catalog.get_resolved_agent_tool_catalog())
    )

    assert entry["connection_status"] == "unavailable"
    assert entry["dynamic_tools"] is True
    assert entry["tools"] == []
