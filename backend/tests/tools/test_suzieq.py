from typing import cast

import httpx
import pytest
from haystack.components.agents import State

from app.core.config import project_settings
from app.infrastructure import InfrastructureClients
from app.tools import suzieq_tools


class FakeClients(InfrastructureClients):
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def request(self, connector: str, method: str, url: str, **kwargs):
        self.requests.append(
            {"connector": connector, "method": method, "url": url, **kwargs}
        )
        return httpx.Response(
            200,
            json=[{"hostname": "edge-01", "status": "alive"}],
            request=httpx.Request(method, url),
        )


@pytest.mark.anyio
async def test_device_tool_uses_shared_async_client(monkeypatch) -> None:
    monkeypatch.setattr(project_settings, "SUZIEQ_ENABLED", True)
    monkeypatch.setattr(project_settings, "SUZIEQ_API_URL", "https://sq.example")
    clients = FakeClients()
    state = State(schema={}, data={"hook_context": {"clients": clients}})

    result = await suzieq_tools.get_devices.invoke_async(
        agent_state=state,
        namespace="prod",
    )

    assert suzieq_tools.get_devices.function is None
    devices = cast(list[dict[str, object]], result["devices"])
    assert devices[0]["hostname"] == "edge-01"
    assert clients.requests[0]["connector"] == "suzieq"
    params = cast(dict[str, object], clients.requests[0]["params"])
    assert params["namespace"] == "prod"
