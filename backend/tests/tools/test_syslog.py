import httpx
import pytest
from haystack.components.agents import State

from app.infrastructure import InfrastructureClients
from app.tools import syslog_tool
from app.tools._syslog_tool_mock import get_host_syslogs


def _invoke_tool(tool_obj, **kwargs):
    if not hasattr(tool_obj, "invoke"):
        raise AssertionError("Expected a tool object with an .invoke method")
    try:
        return tool_obj.invoke(kwargs)
    except TypeError:
        return tool_obj.invoke(**kwargs)


def test_get_syslog_logs_filters_by_hostname() -> None:
    payload = _invoke_tool(get_host_syslogs, hostname="dist-rtr-nyc-01")

    assert payload["count"] >= 1
    assert all("dist-rtr-nyc-01" in row["hostname"].lower() for row in payload["logs"])


def test_get_syslog_logs_filters_by_optional_severity() -> None:
    payload = _invoke_tool(get_host_syslogs, hostname="dist-rtr-nyc-01", severity=3)

    assert payload["count"] >= 1
    assert all(int(row["severity"]) == 3 for row in payload["logs"])


def test_get_syslog_logs_returns_error_for_invalid_severity() -> None:
    payload = _invoke_tool(get_host_syslogs, hostname="dist-rtr-nyc-01", severity=99)

    assert payload["count"] == 0
    assert payload["error"] == "severity_out_of_range:-1_to_7"


class FakeClients(InfrastructureClients):
    def __init__(self) -> None:
        self.content = ""

    async def request(self, connector: str, method: str, url: str, **kwargs):
        self.content = str(kwargs.get("content") or "")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "event_id": "evt-1",
                        "hostname": "dist-rtr-nyc-01",
                        "severity": 3,
                        "raw_message": "interface down",
                    }
                ]
            },
            request=httpx.Request(method, url),
        )


@pytest.mark.anyio
async def test_live_syslog_tool_is_native_async_and_uses_shared_client() -> None:
    clients = FakeClients()
    state = State(schema={}, data={"hook_context": {"clients": clients}})

    result = await syslog_tool.get_host_syslogs.invoke_async(
        agent_state=state,
        hostname="dist-rtr-nyc-01",
        severity=3,
    )

    assert syslog_tool.get_host_syslogs.function is None
    assert result["count"] == 1
    assert "severity = 3" in clients.content
