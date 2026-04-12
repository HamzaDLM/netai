from app.agents.zabbix_agent import (
    ZABBIX_SPECIALIST_PROMPT,
    zabbix_agent,
    zabbix_specialist_tool,
    zabbix_tools,
)


def test_zabbix_prompt_mentions_monitoring_and_evidence() -> None:
    lowered = ZABBIX_SPECIALIST_PROMPT.lower()
    assert "zabbix" in lowered
    assert "evidence" in lowered
    assert "uncertainty" in lowered


def test_zabbix_specialist_toolset_is_populated() -> None:
    assert zabbix_specialist_tool.name == "zabbix_specialist"
    assert zabbix_agent.system_prompt == ZABBIX_SPECIALIST_PROMPT
    assert len(zabbix_tools) >= 5
