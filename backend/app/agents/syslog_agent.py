from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.llm import llm
from app.tools.syslog_tool import get_syslog_evidence

SYSLOG_SPECIALIST_PROMPT = """
You are a syslog specialist agent focused on network syslog analysis.

Always call `syslog.get_evidence` before answering operational questions.
Use only tool evidence when making claims, be explicit about uncertainty,
and suggest the most useful follow-up query when evidence is weak.
"""

syslog_tools: list[Tool] = [
    cast(Tool, get_syslog_evidence),
]

syslog_agent = Agent(
    chat_generator=llm,
    system_prompt=SYSLOG_SPECIALIST_PROMPT,
    tools=syslog_tools,
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
