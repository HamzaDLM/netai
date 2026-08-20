# MCP boundary

MCP is an external protocol adapter, not NetAI's internal orchestration layer.
The internal Agent calls the registered Haystack tools directly.

## Expose NetAI tools

`mcp_server.py` converts a Haystack `Tool` into a FastMCP `FunctionTool` and
delegates execution to `Tool.invoke_async()`. The example publishes a curated,
read-only Zabbix set:

```bash
uv run mcp-zabbix-server --host 127.0.0.1 --port 8030
uv run mcp-zabbix-server --real-data --all-tools
```

For a host that exposes more than one MCP server, pass a JSON list to the
supervisor entrypoint. One systemd process owns all HTTP listeners and stops
all of them together if the process is restarted:

```json
[
  {
    "name": "zabbix",
    "connector": "zabbix",
    "host": "127.0.0.1",
    "port": 8030,
    "transport": "http",
    "use_mock_data": false,
    "tool_names": ["zabbix_get_hosts", "zabbix_get_problems"]
  },
  {
    "name": "suzieq",
    "connector": "suzieq",
    "host": "127.0.0.1",
    "port": 8031,
    "transport": "http",
    "tool_names": ["suzieq_get_devices", "suzieq_get_interfaces"]
  }
]
```

Run it with:

```bash
uv run python -m app.mcp.mcp_server --config /etc/netai/mcp-servers.json
```

The Ansible `netai-mcp-servers` systemd service renders this configuration
and runs the same supervisor. Each instance must have a unique name and
host/port pair.

The HTTP endpoint is `http://127.0.0.1:8030/mcp`. The example has no transport
authentication; keep it private or place it behind an authenticated gateway.

The generic adapter reuses existing tools:

```python
from app.mcp.mcp_server import create_mcp_server
from app.tools.zabbix_tools import diagnose_host, get_hosts

server = create_mcp_server([get_hosts, diagnose_host], name="Monitoring")
```

## Consume Infrahub

`InfrahubToolProvider` creates Haystack's native `MCPToolset` from
`MCPClientConfig`. Discovery is lazy, mutating tool names are filtered, failures
are cached briefly, and failure never prevents startup or unrelated requests.
The service closes a connected toolset during FastAPI shutdown.

```bash
INFRAHUB_MCP_URL=http://127.0.0.1:8001/mcp
INFRAHUB_MCP_TOKEN=
INFRAHUB_MCP_TIMEOUT_SECONDS=5
```

Use read-only credentials and enforce permissions at the Infrahub/MCP server;
the local name filter and Agent authorization hook are defense in depth.
