import app.api.endpoints.chat as chat_endpoints


def test_event_actor_for_specialist_events() -> None:
    actor_type, actor_name = chat_endpoints._event_actor(
        {"type": "specialist_tool_call", "specialist": "syslog"}
    )
    assert actor_type == "specialist"
    assert actor_name == "syslog"


def test_event_actor_for_orchestrator_plan() -> None:
    actor_type, actor_name = chat_endpoints._event_actor({"type": "orchestrator_plan"})
    assert actor_type == "orchestrator"
    assert actor_name == "orchestrator"


def test_event_actor_for_thinking_event_uses_agent_field() -> None:
    actor_type, actor_name = chat_endpoints._event_actor(
        {"type": "thinking", "agent": "zabbix"}
    )
    assert actor_type == "specialist"
    assert actor_name == "zabbix"


def test_event_actor_defaults_to_system_for_unknown_event() -> None:
    actor_type, actor_name = chat_endpoints._event_actor({"type": "custom_thing"})
    assert actor_type == "system"
    assert actor_name == "custom_thing"
