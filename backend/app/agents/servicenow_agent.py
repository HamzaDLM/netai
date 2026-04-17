from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._servicenow_tools_mock import (
        get_change_request,
        get_ci,
        get_incident,
        get_known_cis,
        get_problem,
        get_service_summary,
        list_change_requests,
        list_cis,
        list_incidents,
        list_problems,
    )
else:
    from app.tools.servicenow_tools import (
        get_change_request,
        get_ci,
        get_incident,
        get_known_cis,
        get_problem,
        get_service_summary,
        list_change_requests,
        list_cis,
        list_incidents,
        list_problems,
    )

SERVICENOW_SPECIALIST_PROMPT = """
You are a ServiceNow specialist agent.

Use ServiceNow tools to answer incident/change/problem/CMDB questions.
Return concise, evidence-backed answers and clearly state unknowns.
"""

servicenow_tools: list[Tool] = [
    cast(Tool, get_known_cis),
    cast(Tool, list_incidents),
    cast(Tool, get_incident),
    cast(Tool, list_change_requests),
    cast(Tool, get_change_request),
    cast(Tool, list_problems),
    cast(Tool, get_problem),
    cast(Tool, list_cis),
    cast(Tool, get_ci),
    cast(Tool, get_service_summary),
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
    outputs_to_string={"source": "last_message"},
)
