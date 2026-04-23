from app.agents.zabbix_agent import (
    ZABBIX_SPECIALIST_PROMPT,
    zabbix_agent,
    zabbix_specialist_tool,
    zabbix_tools,
)
from app.prompts.tools_prompt import TOOLS_PROMPT


def test_zabbix_prompt_mentions_planning_capabilities_and_evidence() -> None:
    lowered = ZABBIX_SPECIALIST_PROMPT.lower()
    assert "zabbix" in lowered
    assert "create a short execution plan" in lowered
    assert "evidence" in lowered
    assert "capabilities" in lowered


def test_zabbix_specialist_toolset_is_populated_with_new_api_surface() -> None:
    assert zabbix_specialist_tool.name == "zabbix_specialist"
    assert zabbix_agent.system_prompt == ZABBIX_SPECIALIST_PROMPT

    tool_names = {getattr(tool, "name", "") for tool in zabbix_tools}
    assert "zabbix_get_hosts" in tool_names
    assert "zabbix_get_host_details" in tool_names
    assert "zabbix_diagnose_host" in tool_names
    assert "zabbix_get_zabbix_server_status" in tool_names

    # legacy names removed from exposed surface
    assert "zabbix_list_hosts" not in tool_names
    assert "zabbix_get_host_status" not in tool_names
    assert "zabbix_get_problem_summary" not in tool_names


def test_tools_prompt_zabbix_section_uses_new_names_only() -> None:
    assert "zabbix_get_hosts(" in TOOLS_PROMPT
    assert "zabbix_get_host_details(" in TOOLS_PROMPT
    assert "zabbix_diagnose_host(" in TOOLS_PROMPT

    assert "zabbix_list_hosts(" not in TOOLS_PROMPT
    assert "zabbix_get_host_status(" not in TOOLS_PROMPT
    assert "zabbix_get_problem_summary(" not in TOOLS_PROMPT
