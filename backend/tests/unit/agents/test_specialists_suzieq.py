from app.agents.suzieq_agent import (
    SUZIEQ_SPECIALIST_PROMPT,
    suzieq_agent,
    suzieq_specialist_tool,
    suzieq_tools,
)


def test_suzieq_prompt_mentions_state_and_actionability() -> None:
    lowered = SUZIEQ_SPECIALIST_PROMPT.lower()
    assert "suzieq" in lowered
    assert "actionable" in lowered
    assert "evidence" in lowered


def test_suzieq_specialist_toolset_is_populated() -> None:
    assert suzieq_specialist_tool.name == "suzieq_specialist"
    assert suzieq_agent.system_prompt == SUZIEQ_SPECIALIST_PROMPT
    assert len(suzieq_tools) >= 8
