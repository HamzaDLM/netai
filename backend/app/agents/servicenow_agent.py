from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm
from app.tools import _servicenow_tools_mock as _servicenow_tools_mock_impl
from app.tools import servicenow_tools as _servicenow_tools_impl

_servicenow_tools_module = (
    _servicenow_tools_mock_impl
    if project_settings.TOOLS_USE_MOCK_DATA
    else _servicenow_tools_impl
)

SERVICENOW_SPECIALIST_PROMPT = """
You are a ServiceNow specialist agent.

Use ServiceNow tools to answer incident/change/problem/CMDB questions.
Return concise, evidence-backed answers and clearly state unknowns.
"""

servicenow_tools: list[Tool] = [
    cast(Tool, _servicenow_tools_module.get_known_cis),
    cast(Tool, _servicenow_tools_module.list_incidents),
    cast(Tool, _servicenow_tools_module.get_incident),
    cast(Tool, _servicenow_tools_module.list_change_requests),
    cast(Tool, _servicenow_tools_module.get_change_request),
    cast(Tool, _servicenow_tools_module.list_problems),
    cast(Tool, _servicenow_tools_module.get_problem),
    cast(Tool, _servicenow_tools_module.list_cis),
    cast(Tool, _servicenow_tools_module.get_ci),
    cast(Tool, _servicenow_tools_module.get_service_summary),
]

servicenow_agent = Agent(
    chat_generator=llm,
    system_prompt=SERVICENOW_SPECIALIST_PROMPT,
    tools=servicenow_tools,
    max_agent_steps=10,
)


servicenow_specialist_tool = ComponentTool(
    component=servicenow_agent,
    name="servicenow_specialist",
    description=(
        "ITSM/CMDB specialist. Use for incidents, problems, change requests, "
        "CI records, service summaries, and operational ticket context."
    ),
)
