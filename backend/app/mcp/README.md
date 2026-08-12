# NetAI MCP integration

NetAI can expose its existing Haystack tools as an MCP server and consume tools
from any streamable-HTTP MCP server. The example server publishes a conservative,
read-only Zabbix set: host search, active problems, server health, and host
diagnosis.

## Run the Zabbix server

From `backend/`:

```bash
# Uses NetAI's deterministic Zabbix mock data
uv run mcp-zabbix-server

# Inspect the tools from another terminal
uv run mcp-client

# Call one
uv run mcp-client zabbix_get_hosts '{"status":"down","limit":10}'
uv run mcp-client zabbix_diagnose_host '{"hostname_or_ip":"edge-fw-par-01"}'
```

The HTTP endpoint is `http://127.0.0.1:8030/mcp`. A stdio server is also
available with `uv run mcp-zabbix-server --transport stdio`.

For a real Zabbix instance, configure the same environment used by NetAI's
native Zabbix tools, then opt in explicitly:

```bash
export ZABBIX_API_URL='https://zabbix.example/api_jsonrpc.php'
export ZABBIX_API_TOKEN='replace-me'
uv run mcp-zabbix-server --real-data
```

Do not bind the unauthenticated example server to a public interface. Put it
behind an authenticated MCP gateway/reverse proxy before remote deployment.

## Wire existing tools to a server

The Zabbix factory supports both a curated set and every current Zabbix tool:

```python
from app.mcp.mcp_server import create_zabbix_mcp_server

# A hand-picked server for one workflow.
server = create_zabbix_mcp_server(
    use_mock_data=False,
    tool_names=("zabbix_get_hosts", "zabbix_get_problems"),
)
server.run(transport="http", host="127.0.0.1", port=8030)

# Or expose all Zabbix tools (equivalent CLI: --all-tools).
all_zabbix = create_zabbix_mcp_server(use_mock_data=False, tool_names=None)
```

The generic adapter works for another NetAI integration without MCP-specific
wrappers:

```python
from app.mcp.mcp_server import create_mcp_server
from app.tools.zabbix_tools import get_hosts, diagnose_host

server = create_mcp_server([get_hosts, diagnose_host], name="Network monitoring")
```

## Consume the server

For direct application calls:

```python
from app.mcp.mcp_client import NetAIMCPClient

async with NetAIMCPClient("http://127.0.0.1:8030/mcp") as client:
    available = await client.list_tools()
    diagnosis = await client.call_tool(
        "zabbix_diagnose_host",
        {"hostname_or_ip": "edge-fw-par-01", "hours": 12},
    )
```

To give remotely hosted tools to a Haystack agent:

```python
from haystack.components.agents import Agent
from app.mcp.mcp_client import MCPClientConfig, discover_haystack_tools

remote_tools = await discover_haystack_tools(
    MCPClientConfig(url="http://127.0.0.1:8030/mcp"),
    include={"zabbix_get_hosts", "zabbix_get_problems"},
)
agent = Agent(chat_generator=llm, tools=remote_tools)

# At application shutdown:
for tool in remote_tools:
    tool.close()
```
