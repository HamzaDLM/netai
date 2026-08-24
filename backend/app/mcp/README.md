# MCP boundary

MCP is an external protocol adapter, not NetAI's internal orchestration layer.
The internal Agent calls the registered Haystack tools directly.

## Expose NetAI tools

`mcp_server.py` converts each registered Haystack `Tool` into a FastMCP
`FunctionTool`, delegates execution to `Tool.invoke_async()`, and exposes only
the connectors and tool names declared in the runtime configuration:

```bash
uv run mcp-server
```

For a host that exposes more than one MCP server, edit `MCP_SERVERS` in
`mcp_server.py`. It is a Python tuple, so tool names can be kept close to the
server implementation without a second configuration format:

```python
from app.mcp.mcp_server import MCPServerConfig

MCP_SERVERS = (
    MCPServerConfig(
        name="zabbix",
        connector="zabbix",
        description="Read-only Zabbix monitoring, host inventory, and active problem data.",
        allowed_consumer_urls=("https://netai.example.com",),
        host="127.0.0.1",
        port=8030,
        transport="http",
        tool_names=("zabbix_get_hosts", "zabbix_get_problems"),
    ),
    MCPServerConfig(
        name="suzieq",
        connector="suzieq",
        description="Read-only SuzieQ network state and control-plane data.",
        allowed_consumer_urls=("https://netai.example.com",),
        host="127.0.0.1",
        port=8031,
        transport="http",
        tool_names=("suzieq_get_devices", "suzieq_get_interfaces"),
    ),
)
```

One systemd process owns all HTTP listeners and stops all of them together if
the process is restarted. Run it with:

```bash
uv run python -m app.mcp.mcp_server
```

The Ansible `netai-mcp-servers` systemd service runs the same module. Each
instance must have a unique name and host/port pair. Clients must send the
configured bearer token and either an `Origin` header or
`X-MCP-Consumer-URL` matching the server's `allowed_consumer_urls`.

Set the shared token in `MCP_CONSUMER_TOKEN`. This is bearer-token resource
server authentication using FastMCP's token-verifier API; it does not issue
OAuth tokens or implement an interactive authorization-code flow. Replace
`SharedTokenVerifier` with a JWT or introspection verifier when an external
OAuth provider is introduced.

The HTTP endpoint is `http://127.0.0.1:8030/mcp`. Keep the token in the
environment and place the service behind TLS or an authenticated gateway when
it is reachable outside the local host.

## Standalone Zabbix server

`zabbix_server.py` is a self-contained FastMCP server copy of the Zabbix
integration. It has no NetAI or Haystack imports; the functions are registered
directly with FastMCP. Configure the Zabbix connection with environment
variables and run it independently:

```bash
export ZABBIX_ENABLED=true
export ZABBIX_API_URL=https://zabbix.example.com/api_jsonrpc.php
export ZABBIX_API_TOKEN=...
export MCP_HOST=127.0.0.1
export MCP_PORT=8030
uv run mcp-zabbix-standalone
```

## Consume external MCP connectors

This section applies only to external MCP servers consumed by NetAI, such as
Infrahub and SuzieQ. It does not change the MCP servers that expose NetAI's own
tools.

At FastAPI startup, each provider opens one persistent FastMCP client session,
checks the server's advertised capabilities, and caches metadata returned by
`tools/list`, `prompts/list`, and `resources/list` where supported. It never
loads prompt or resource bodies at startup. Discovered read-only MCP tools are
adapted directly to native Haystack `Tool` objects; mutating tool names are
filtered.

At request time, generic metadata matching routes only relevant connectors and
selects relevant prompt/resource entries. Prompt content is retrieved with
`prompts/get` and cached after its first use. Text resources are retrieved with
`resources/read` and cached for the configured TTL. Selected prompt content is
added as supplemental agent instructions and selected resources as untrusted
request reference data. Required-argument prompts are not fetched
automatically because NetAI cannot safely invent their arguments. Tools-only
servers continue to work without any prompt/resource calls.

Connection and individual capability failures are isolated so an unavailable
external MCP server never prevents the Agent from using other connectors. The
service closes every persistent client at FastAPI shutdown. When SuzieQ MCP is
reachable and exposes read-only tools, it takes precedence over the direct
SuzieQ API tools for that request; otherwise NetAI retains the direct tools as
a fallback.

```bash
INFRAHUB_MCP_URL=http://127.0.0.1:8001/mcp
INFRAHUB_MCP_TOKEN=
INFRAHUB_MCP_TIMEOUT_SECONDS=5
INFRAHUB_MCP_RESOURCE_TTL_SECONDS=60

SUZIEQ_MCP_URL=http://127.0.0.1:8002/mcp
SUZIEQ_MCP_TOKEN=
SUZIEQ_MCP_TIMEOUT_SECONDS=5
SUZIEQ_MCP_RESOURCE_TTL_SECONDS=60
```

Use read-only credentials and enforce permissions at each upstream MCP server;
the local name filter and Agent authorization hook are defense in depth.
