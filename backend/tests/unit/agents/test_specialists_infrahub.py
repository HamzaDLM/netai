from haystack_integrations.tools.mcp import StreamableHttpServerInfo

from app.agents.infrahub_agent import (
    INFRAHUB_SPECIALIST_PROMPT,
    infrahub_agent,
    infrahub_specialist_tool,
    infrahub_tools,
)
from app.core.config import project_settings
from app.mcp.mcp_client import infrahub_mcp
from app.mcp.mcp_component_tool import IsolatedMCPComponentTool


def test_infrahub_specialist_uses_configured_lazy_mcp_toolset() -> None:
    assert infrahub_specialist_tool.name == "infrahub_specialist"
    assert isinstance(infrahub_specialist_tool, IsolatedMCPComponentTool)
    assert infrahub_agent.tools is infrahub_tools
    assert infrahub_tools.eager_connect is False
    assert isinstance(infrahub_tools.server_info, StreamableHttpServerInfo)
    assert infrahub_tools.server_info.url == project_settings.INFRAHUB_MCP_URL
    assert infrahub_mcp.url == project_settings.INFRAHUB_MCP_URL


def test_infrahub_specialist_is_read_only() -> None:
    lowered = INFRAHUB_SPECIALIST_PROMPT.lower()
    assert "read-only" in lowered
    assert "never invoke" in lowered


def test_infrahub_parent_warm_up_does_not_connect(monkeypatch) -> None:
    def fail_if_warmed() -> None:
        raise AssertionError("nested Infrahub agent must not warm here")

    monkeypatch.setattr(infrahub_agent, "warm_up", fail_if_warmed)

    infrahub_specialist_tool.warm_up()


def test_infrahub_failure_is_contained_at_delegation_boundary(monkeypatch) -> None:
    def fail_run(**_kwargs):
        raise ConnectionError("Infrahub is offline")

    monkeypatch.setattr(infrahub_agent, "run", fail_run)

    result = infrahub_specialist_tool.invoke(messages=[])

    assert result["error"] == "mcp_specialist_unavailable"
    assert result["specialist"] == "infrahub_specialist"
    assert result["available"] is False
