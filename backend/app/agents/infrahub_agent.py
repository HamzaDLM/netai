from haystack.components.agents import Agent
from haystack_integrations.tools.mcp import MCPToolset

from app.llm import llm
from app.mcp.mcp_client import create_haystack_toolset, infrahub_mcp
from app.mcp.mcp_component_tool import IsolatedMCPComponentTool

INFRAHUB_SPECIALIST_PROMPT = """
You are an Infrahub infrastructure source-of-truth specialist agent.

Use the Infrahub MCP tools for infrastructure inventory, schema, relationships,
topology, intended state, and other Infrahub-backed context. Ground every answer
in tool results and clearly distinguish missing data from a negative finding.

Operate read-only. Never invoke a tool that creates, updates, deletes, merges,
approves, or otherwise mutates Infrahub data, even if the MCP server exposes it.
If the request requires a mutation, explain that this specialist is read-only.

If the user asks what tools or capabilities you have, respond with a plain-text
summary of the currently available Infrahub tools. Do not invoke a tool merely
to demonstrate it.
"""

# Discovery and connection are deferred until this specialist is actually invoked.
infrahub_tools: MCPToolset = create_haystack_toolset(infrahub_mcp)

infrahub_agent = Agent(
    chat_generator=llm,
    system_prompt=INFRAHUB_SPECIALIST_PROMPT,
    tools=infrahub_tools,
    max_agent_steps=10,
)

infrahub_specialist_tool = IsolatedMCPComponentTool(
    component=infrahub_agent,
    name="infrahub_specialist",
    description=(
        "Read-only Infrahub source-of-truth specialist. Use for infrastructure "
        "inventory, schemas, relationships, topology, and intended-state context."
    ),
)


def close_infrahub_tools() -> None:
    """Release the persistent MCP worker, if the specialist was used."""

    infrahub_tools.close()
