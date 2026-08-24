import asyncio

from fastmcp import Client

from app.mcp.zabbix_server import ZabbixSettings, mcp


def test_standalone_zabbix_server_registers_fastmcp_tools() -> None:
    async def exercise() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()

        names = {tool.name for tool in tools}
        assert "zabbix_get_hosts" in names
        assert "zabbix_diagnose_host" in names

    asyncio.run(exercise())


def test_standalone_zabbix_settings_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ZABBIX_ENABLED", "true")
    monkeypatch.setenv("ZABBIX_API_URL", "https://zabbix.example.test/api_jsonrpc.php")
    monkeypatch.setenv("ZABBIX_API_TOKEN", "secret")
    monkeypatch.setenv("ZABBIX_TIMEOUT_SECONDS", "7")

    settings = ZabbixSettings.from_environment()

    assert settings.enabled is True
    assert settings.api_url.endswith("api_jsonrpc.php")
    assert settings.api_token == "secret"
    assert settings.timeout_seconds == 7
