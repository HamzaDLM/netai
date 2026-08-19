# NetAI backend

The backend is a FastAPI application centered on one lifecycle-owned
`NetAIService` and one Haystack 3 `Agent`.

```text
FastAPI lifespan
  -> NetAIService
     -> ChatGenerator
     -> Agent.run_async()
        -> SearchableToolset
           -> native Haystack Tools
              -> shared infrastructure clients
```

`app/tools/registry.py` is the single source of truth for local Agent tools and
the connector catalogue. Cross-cutting authorization and execution events live
in Agent hooks, while Haystack state carries request/user context and native run
counters. `app/mcp` contains external protocol adapters only.

HTTP integrations (SuzieQ, ServiceNow, and ClickHouse) are async and reuse
lifespan-owned `httpx.AsyncClient` pools. Two deliberate synchronous boundaries
remain: pyzabbix and local git CLI commands. Haystack's native async Tool
fallback dispatches those sync-only libraries off the event loop.

See [the repository README](../README.md) for setup and configuration and
[the MCP notes](app/mcp/README.md) for the external Zabbix adapter.
