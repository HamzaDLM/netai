from app.agents.security_agent import (
    SECURITY_SPECIALIST_PROMPT,
    security_agent,
    security_specialist_tool,
    security_tools,
)


def test_security_prompt_mentions_hardening_and_vulns() -> None:
    lowered = SECURITY_SPECIALIST_PROMPT.lower()
    assert "hardening" in lowered
    assert "vulnerabilities" in lowered
    assert "cves" in lowered


def test_security_specialist_registration_is_valid() -> None:
    assert security_specialist_tool.name == "security_specialist"
    assert security_agent.system_prompt == SECURITY_SPECIALIST_PROMPT
    assert security_tools == []
