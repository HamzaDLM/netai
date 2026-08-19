from typing import cast

import httpx
import pytest
from haystack.components.agents import State

from app.core.config import project_settings
from app.infrastructure import InfrastructureClients
from app.tools import servicenow_tools


class FakeClients(InfrastructureClients):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.requests: list[dict[str, object]] = []

    async def request(self, connector: str, method: str, url: str, **kwargs):
        self.requests.append(
            {"connector": connector, "method": method, "url": url, **kwargs}
        )
        return httpx.Response(
            200,
            json={"result": self.rows},
            request=httpx.Request(method, url),
        )


def _state(clients: InfrastructureClients) -> State:
    return State(schema={}, data={"hook_context": {"clients": clients}})


@pytest.mark.anyio
async def test_incident_tool_uses_shared_async_client(monkeypatch) -> None:
    monkeypatch.setattr(project_settings, "SERVICENOW_ENABLED", True)
    monkeypatch.setattr(
        project_settings, "SERVICENOW_INSTANCE_URL", "https://snow.example"
    )
    monkeypatch.setattr(project_settings, "SERVICENOW_ACCESS_TOKEN", "token")
    clients = FakeClients(
        [
            {
                "number": "INC001",
                "state": "1",
                "priority": "2",
                "short_description": "WAN down",
            }
        ]
    )

    result = await servicenow_tools.list_incidents.invoke_async(
        agent_state=_state(clients),
        state="new",
    )

    assert servicenow_tools.list_incidents.function is None
    assert result["count"] == 1
    incidents = cast(list[dict[str, object]], result["incidents"])
    assert incidents[0]["number"] == "INC001"
    assert clients.requests[0]["connector"] == "servicenow"
    params = cast(dict[str, object], clients.requests[0]["params"])
    assert "state=1" in cast(str, params["sysparm_query"])
