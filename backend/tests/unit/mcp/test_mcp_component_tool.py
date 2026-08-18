from typing import Any

from haystack import component
from haystack.tools import warm_up_tools

from app.mcp.mcp_component_tool import IsolatedMCPComponentTool


@component
class _FailingMCPComponent:
    def __init__(self) -> None:
        self.warm_up_calls = 0

    def warm_up(self) -> None:
        self.warm_up_calls += 1
        raise ConnectionError("MCP endpoint is offline")

    @component.output_types(result=dict[str, Any])
    def run(self, query: str) -> dict[str, Any]:
        raise ConnectionError(f"MCP endpoint is offline for {query}")


def test_parent_warm_up_does_not_connect_nested_mcp_component() -> None:
    nested_component = _FailingMCPComponent()
    specialist = IsolatedMCPComponentTool(
        component=nested_component,
        name="offline_specialist",
        description="Test specialist",
    )

    warm_up_tools([specialist])

    assert nested_component.warm_up_calls == 0


def test_mcp_invocation_failure_becomes_structured_tool_result() -> None:
    specialist = IsolatedMCPComponentTool(
        component=_FailingMCPComponent(),
        name="offline_specialist",
        description="Test specialist",
    )

    result = specialist.invoke(query="router-01")

    assert result == {
        "error": "mcp_specialist_unavailable",
        "specialist": "offline_specialist",
        "available": False,
        "retryable": True,
        "message": (
            "The offline_specialist service is currently unavailable. "
            "Continue with other specialists when they can answer the request."
        ),
        "error_type": "ConnectionError",
    }
