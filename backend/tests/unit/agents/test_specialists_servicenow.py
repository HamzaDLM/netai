from app.agents.servicenow_agent import (
    SERVICENOW_SPECIALIST_PROMPT,
    servicenow_agent,
    servicenow_specialist_tool,
    servicenow_tools,
)


def test_servicenow_prompt_mentions_itsm_and_unknowns() -> None:
    lowered = SERVICENOW_SPECIALIST_PROMPT.lower()
    assert "servicenow" in lowered
    assert "incident/change/problem/cmdb" in lowered
    assert "unknown" in lowered


def test_servicenow_specialist_toolset_is_populated() -> None:
    assert servicenow_specialist_tool.name == "servicenow_specialist"
    assert servicenow_agent.system_prompt == SERVICENOW_SPECIALIST_PROMPT
    assert len(servicenow_tools) >= 8
