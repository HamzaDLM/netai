from app.agents.orchestrator_agent import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    SPECIALIST_DESCRIPTIONS,
    orchestrator_agent,
)

EXPECTED_SPECIALISTS = {
    "zabbix_specialist",
    "suzieq_specialist",
    "servicenow_specialist",
    "datamodel_specialist",
    "syslog_specialist",
    "security_specialist",
}


def test_orchestrator_prompt_contains_routing_policy() -> None:
    lowered = ORCHESTRATOR_SYSTEM_PROMPT.lower()
    assert "routing policy" in lowered
    assert "never invent tool outputs" in lowered
    assert "delegate" in lowered


def test_orchestrator_exposes_expected_specialists() -> None:
    tool_names = {getattr(tool, "name", "") for tool in orchestrator_agent.tools}
    assert EXPECTED_SPECIALISTS.issubset(tool_names)
    assert "zabbix" in SPECIALIST_DESCRIPTIONS
    assert "syslog" in SPECIALIST_DESCRIPTIONS
