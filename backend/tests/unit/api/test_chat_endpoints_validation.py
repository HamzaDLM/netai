import app.services.chat_runs as chat_runs


def test_event_actor_for_tool_lifecycle() -> None:
    actor_type, actor_name = chat_runs._event_actor(
        {"type": "tool_started", "tool_name": "syslog_get_host_syslogs"}
    )
    assert actor_type == "tool"
    assert actor_name == "syslog_get_host_syslogs"


def test_event_actor_for_artifact() -> None:
    actor_type, actor_name = chat_runs._event_actor(
        {"type": "artifact_delta", "kind": "network.topology.v1"}
    )
    assert actor_type == "tool"
    assert actor_name == "network.topology.v1"


def test_event_actor_defaults_to_system_for_unknown_event() -> None:
    actor_type, actor_name = chat_runs._event_actor({"type": "custom_thing"})
    assert actor_type == "system"
    assert actor_name == "custom_thing"
