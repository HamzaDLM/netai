from app.agents.syslog_agent import (
    SYSLOG_SPECIALIST_PROMPT,
    syslog_agent,
    syslog_specialist_tool,
    syslog_tools,
)


def test_syslog_prompt_sets_evidence_first_guardrails() -> None:
    lowered = SYSLOG_SPECIALIST_PROMPT.lower()
    assert "always call" in lowered
    assert "syslog.get_evidence" in lowered
    assert "syslog.get_logs" in lowered
    assert "uncertainty" in lowered


def test_syslog_specialist_has_expected_registration() -> None:
    assert syslog_specialist_tool.name == "syslog_specialist"
    assert syslog_agent.system_prompt == SYSLOG_SPECIALIST_PROMPT
    assert len(syslog_tools) >= 2
