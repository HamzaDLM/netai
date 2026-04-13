from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._zabbix_tools_mock import (
        get_host_interfaces,
        get_host_inventory,
        get_host_metrics,
        get_host_status,
        get_problem_summary,
        get_trigger_events,
        list_zabbix_hosts,
    )
else:
    from app.tools.zabbix_tools import (
        get_host_interfaces,
        get_host_inventory,
        get_host_metrics,
        get_host_status,
        get_problem_summary,
        get_trigger_events,
        list_zabbix_hosts,
    )

ZABBIX_SPECIALIST_PROMPT = """
You are a Zabbix specialist agent.

Focus on monitoring and inventory troubleshooting using only Zabbix tools.
Be concise, include evidence from tool outputs, and call out uncertainty clearly.

When answering, if you're referencing a host's status, it will be prefered if you can add appropriate ANSI colors to showcase the severity. 
e.g.: up = green, down = red
"""

zabbix_tools: list[Tool] = [
    cast(Tool, list_zabbix_hosts),
    cast(Tool, get_host_status),
    cast(Tool, get_host_inventory),
    cast(Tool, get_host_interfaces),
    cast(Tool, get_host_metrics),
    cast(Tool, get_trigger_events),
    cast(Tool, get_problem_summary),
]

zabbix_agent = Agent(
    chat_generator=llm,
    system_prompt=ZABBIX_SPECIALIST_PROMPT,
    tools=zabbix_tools,
)

zabbix_specialist_tool = ComponentTool(
    component=zabbix_agent,
    name="zabbix_specialist",
    description=(
        "Monitoring specialist. Use for Zabbix host status, triggers, inventory, "
        "interfaces, metrics, and problem-event analysis."
    ),
    outputs_to_string={"source": "last_message"},
)
