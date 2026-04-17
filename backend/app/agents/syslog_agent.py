from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._syslog_tool_mock import get_syslog_evidence, get_syslog_logs
else:
    from app.tools.syslog_tool import get_syslog_evidence, get_syslog_logs

SYSLOG_SPECIALIST_PROMPT = """
You are a syslog specialist agent focused on network syslog analysis.

Always call `syslog.get_evidence` before answering operational questions.
Use `syslog.get_logs` for exact hostname/severity recent-event lookups.
Use only tool evidence when making claims, be explicit about uncertainty,
and suggest the most useful follow-up query when evidence is weak.
"""

syslog_tools: list[Tool] = [
    cast(Tool, get_syslog_evidence),
    cast(Tool, get_syslog_logs),
]

syslog_agent = Agent(
    chat_generator=llm,
    system_prompt=SYSLOG_SPECIALIST_PROMPT,
    tools=syslog_tools,
    max_agent_steps=10,
)

syslog_specialist_tool = ComponentTool(
    component=syslog_agent,
    name="syslog_specialist",
    description=(
        "Network syslog specialist. Use for ClickHouse/Qdrant-backed syslog evidence "
        "retrieval and incident-oriented syslog analysis."
    ),
    outputs_to_string={"source": "last_message"},
)
