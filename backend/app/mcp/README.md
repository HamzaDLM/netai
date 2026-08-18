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

## Infrahub specialist

The orchestrator includes an `infrahub_specialist` backed by a lazy MCP
toolset. Configure its streamable-HTTP endpoint in `.env`:

```bash
INFRAHUB_MCP_URL=http://127.0.0.1:8001/mcp
INFRAHUB_MCP_TOKEN=
INFRAHUB_MCP_TIMEOUT_SECONDS=30
MCP_CATALOG_DISCOVERY_TIMEOUT_SECONDS=5
```

The specialist toolset does not contact Infrahub while modules are imported,
while the API starts, or while the parent orchestrator warms up. It connects
only when the orchestrator delegates to the specialist, and its connection is
released during API shutdown. The connectors catalogue performs its own bounded,
short-lived discovery when that view is opened; catalogue failures are isolated.

MCP-backed agents must be exposed to a parent agent with
`IsolatedMCPComponentTool`, not a regular `ComponentTool`. Haystack recursively
warms regular component tools; the isolated variant prevents an unavailable MCP
server from affecting unrelated questions and converts a delegated connection
failure into a structured `mcp_specialist_unavailable` tool result.

The specialist is instructed to use read-only operations. Treat that prompt as
defense in depth, not as the authorization boundary: expose only read-only tools
and use read-only Infrahub credentials on the configured MCP server.

MCP-backed agents are added to the connectors catalogue automatically when their
named configuration lives in `app/mcp/mcp_client.py` and their agent follows the
same declaration pattern:

```python
example_mcp = MCPClientConfig(url="http://127.0.0.1:8040/mcp")
example_tools = create_haystack_toolset(example_mcp)

example_specialist_tool = IsolatedMCPComponentTool(
    component=example_agent,
    name="example_specialist",
    description="Example MCP specialist",
)
```

Opening the connectors view performs bounded tool discovery for every detected
MCP agent. A reachable server contributes its live tool names and descriptions;
an unavailable server remains visible with an unavailable status and does not
prevent other connectors from loading.
