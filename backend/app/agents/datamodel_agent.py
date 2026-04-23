from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.llm import llm
from app.tools.datamodel_tools import (
    get_device,
    get_known_fake_devices,
    get_neighbors,
    get_topology,
    list_devices,
    list_links,
)

DATAMODEL_SPECIALIST_PROMPT = """
You are a datamodel/topology specialist agent.

Use datamodel tools to answer topology, neighbor, and inventory questions.
Prefer structured summaries and include relevant evidence.
"""

datamodel_tools: list[Tool] = [
    cast(Tool, get_known_fake_devices),
    cast(Tool, list_devices),
    cast(Tool, get_device),
    cast(Tool, list_links),
    cast(Tool, get_neighbors),
    cast(Tool, get_topology),
]

datamodel_agent = Agent(
    chat_generator=llm,
    system_prompt=DATAMODEL_SPECIALIST_PROMPT,
    tools=datamodel_tools,
    max_agent_steps=10,
)


datamodel_specialist_tool = ComponentTool(
    component=datamodel_agent,
    name="datamodel_specialist",
    description=(
        "Topology and inventory specialist. Use for devices, links, neighbors, and "
        "graph-level infrastructure mapping and relationship questions."
    ),
)
