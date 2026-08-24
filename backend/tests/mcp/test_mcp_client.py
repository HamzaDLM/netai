from collections.abc import Callable
from types import SimpleNamespace

import pytest

from app.mcp import mcp_client
from app.mcp.mcp_client import MCPClientConfig
from app.mcp.suzieq import SuzieQToolProvider


@pytest.fixture(autouse=True)
def run_threaded_lifecycle_inline(monkeypatch) -> None:
    async def run_inline(
        function: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> object:
        return function(*args, **kwargs)

    monkeypatch.setattr(mcp_client.asyncio, "to_thread", run_inline)


class FakeToolset:
    def __init__(self, names: list[str], *, fail_warm_up: bool = False) -> None:
        self.tools = [SimpleNamespace(name=name) for name in names]
        self.fail_warm_up = fail_warm_up
        self.warmed_up = False
        self.closed = False

    def warm_up(self) -> None:
        self.warmed_up = True
        if self.fail_warm_up:
            raise ConnectionError("unavailable")

    def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_suzieq_provider_discovers_only_read_only_tools(monkeypatch) -> None:
    toolset = FakeToolset(["suzieq_get_bgp", "suzieq_update_device"])
    monkeypatch.setattr(mcp_client, "create_haystack_toolset", lambda _config: toolset)
    provider = SuzieQToolProvider(MCPClientConfig(url="http://suzieq.test/mcp"))

    discovered = await provider.get_toolset()

    assert discovered is toolset
    assert [tool.name for tool in toolset.tools] == ["suzieq_get_bgp"]
    assert toolset.tools[0].netai_connector == "suzieq"
    assert provider.status == "available"
    await provider.close()
    assert toolset.closed is True


@pytest.mark.anyio
async def test_suzieq_provider_caches_connection_failure(monkeypatch) -> None:
    toolset = FakeToolset([], fail_warm_up=True)
    calls = 0

    def create(_config: MCPClientConfig) -> FakeToolset:
        nonlocal calls
        calls += 1
        return toolset

    monkeypatch.setattr(mcp_client, "create_haystack_toolset", create)
    provider = SuzieQToolProvider(MCPClientConfig(url="http://suzieq.test/mcp"))

    assert await provider.get_toolset() is None
    assert await provider.get_toolset() is None
    assert provider.status == "unavailable"
    assert provider.status_message == "SuzieQ is currently unavailable."
    assert calls == 1
    assert toolset.closed is True
