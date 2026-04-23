from typing import cast

from haystack.components.agents import Agent
from haystack.tools import Tool

from app.agents.bitbucket_agent import bitbucket_specialist_tool
from app.agents.datamodel_agent import datamodel_specialist_tool
from app.agents.security_agent import security_specialist_tool
from app.agents.servicenow_agent import servicenow_specialist_tool
from app.agents.suzieq_agent import suzieq_specialist_tool
from app.agents.syslog_agent import syslog_specialist_tool
from app.agents.zabbix_agent import zabbix_specialist_tool
from app.llm import llm

SPECIALIST_DESCRIPTIONS: dict[str, str] = {
    "zabbix": "Monitoring and telemetry from Zabbix hosts/triggers/events.",
    "suzieq": "Live network-state and protocol analysis from SuzieQ datasets.",
    "bitbucket": "Repository-backed configuration and change-history analysis.",
    "servicenow": "Operational process and CMDB context from ServiceNow records.",
    "datamodel": "Static infrastructure topology and neighbor relationship analysis.",
    "syslog": "Network syslog evidence and incident patterns from ClickHouse/Qdrant.",
    "security": "Network/security assistant.",
}

ORCHESTRATOR_SYSTEM_PROMPT = f"""
You are the Lead Network Infrastructure Orchestrator in a multi-agent system.

Your responsibilities:
1. Understand user intent and break the request into a short execution plan.
2. Delegate sub-tasks to the right specialist tools.
3. Combine specialist outputs into one clear, evidence-based response.
4. Explicitly state assumptions and uncertainty.
5. Ask for clarification only when the request is ambiguous and blocks progress.

Specialists available:
- zabbix_specialist: {SPECIALIST_DESCRIPTIONS["zabbix"]}
- suzieq_specialist: {SPECIALIST_DESCRIPTIONS["suzieq"]}
- bitbucket_specialist: {SPECIALIST_DESCRIPTIONS["bitbucket"]}
- servicenow_specialist: {SPECIALIST_DESCRIPTIONS["servicenow"]}
- datamodel_specialist: {SPECIALIST_DESCRIPTIONS["datamodel"]}
- syslog_specialist: {SPECIALIST_DESCRIPTIONS["syslog"]}
- security_specialist: {SPECIALIST_DESCRIPTIONS["security"]}

Routing policy:
- Prefer the most specific specialist first.
- Never invent tool outputs; only use delegated results as evidence.
"""

orchestrator_agent = Agent(
    chat_generator=llm,
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    tools=[
        cast(Tool, zabbix_specialist_tool),
        cast(Tool, suzieq_specialist_tool),
        cast(Tool, bitbucket_specialist_tool),
        cast(Tool, servicenow_specialist_tool),
        cast(Tool, datamodel_specialist_tool),
        cast(Tool, syslog_specialist_tool),
        cast(Tool, security_specialist_tool),
    ],
    max_agent_steps=10,
)
