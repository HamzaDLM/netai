from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._suzieq_tools_mock import (
        check_control_plane_health,
        get_arp_nd,
        get_bgp_sessions,
        get_devices,
        get_interfaces,
        get_lldp_neighbors,
        get_mac_table,
        get_ospf_neighbors,
        get_path,
        get_routes,
        infrastructure_summary,
        list_namespaces,
    )
else:
    from app.tools.suzieq_tools import (
        check_control_plane_health,
        get_arp_nd,
        get_bgp_sessions,
        get_devices,
        get_interfaces,
        get_lldp_neighbors,
        get_mac_table,
        get_ospf_neighbors,
        get_path,
        get_routes,
        infrastructure_summary,
        list_namespaces,
    )

SUZIEQ_SPECIALIST_PROMPT = """
You are a SuzieQ specialist agent.

Use SuzieQ tools for multi-vendor state, path, and control-plane health analysis.
Keep output actionable and evidence-based.
"""

suzieq_tools: list[Tool] = [
    cast(Tool, list_namespaces),
    cast(Tool, get_devices),
    cast(Tool, get_interfaces),
    cast(Tool, get_lldp_neighbors),
    cast(Tool, get_bgp_sessions),
    cast(Tool, get_ospf_neighbors),
    cast(Tool, get_routes),
    cast(Tool, get_arp_nd),
    cast(Tool, get_mac_table),
    cast(Tool, get_path),
    cast(Tool, infrastructure_summary),
    cast(Tool, check_control_plane_health),
]

suzieq_agent = Agent(
    chat_generator=llm,
    system_prompt=SUZIEQ_SPECIALIST_PROMPT,
    tools=suzieq_tools,
)

suzieq_specialist_tool = ComponentTool(
    component=suzieq_agent,
    name="suzieq_specialist",
    description=(
        "Network state specialist. Use for BGP/OSPF health, LLDP topology, routes, "
        "ARP/ND, MAC tables, and path analysis from SuzieQ data."
    ),
    outputs_to_string={"source": "last_message"},
)
