import app.api.endpoints.chat as chat_endpoints


def test_derive_tool_source_extracts_prefix_when_namespaced() -> None:
    assert chat_endpoints._derive_tool_source("zabbix.get_host_status") == "zabbix"


def test_derive_tool_source_returns_none_for_empty_or_non_namespaced() -> None:
    assert chat_endpoints._derive_tool_source("") is None
    assert chat_endpoints._derive_tool_source("syslog_specialist") is None


def test_normalize_evidence_entries_uses_existing_evidence() -> None:
    tool = {
        "name": "zabbix.get_host_status",
        "evidence": [{"type": "zabbix", "ref": "host", "content": "up", "score": 0.9}],
    }

    out = chat_endpoints._normalize_evidence_entries(tool)

    assert out == tool["evidence"]


def test_normalize_evidence_entries_falls_back_to_serialized_result() -> None:
    tool = {"name": "syslog_specialist", "result": {"status": "ok"}}

    out = chat_endpoints._normalize_evidence_entries(tool)

    assert len(out) == 1
    assert out[0]["ref"] == "syslog_specialist"
    assert "status" in out[0]["content"]
