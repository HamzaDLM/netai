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
from app.core.config import project_settings
from app.llm import llm
from app.tools.probe_tools import latency_chart, ping, traceroute

SPECIALIST_DESCRIPTIONS: dict[str, str] = {
    "zabbix": "Monitoring and telemetry from Zabbix hosts/triggers/events.",
    "suzieq": "Live network-state and protocol analysis from SuzieQ datasets.",
    "bitbucket": "Repository-backed configuration and change-history analysis.",
    "servicenow": "Operational process and CMDB context from ServiceNow records.",
    "datamodel": "Static infrastructure topology and neighbor relationship analysis.",
    "syslog": "Network syslog evidence and incident patterns from ClickHouse/Qdrant.",
    "security": "Network security and hardening analysis.",
}

_SIMULATED_DIAGNOSTIC_PROMPT = (
    """
Direct diagnostic tools:
- network_ping: safe simulated reachability test with live visual progress.
- network_traceroute: safe simulated hop-by-hop path trace with live visual progress.
- network_latency_chart: safe simulated latency time series rendered as a chart.

The three network_* tools are explicitly simulations for UI development. Always
describe their results as simulated and never present them as measurements from a
real environment.
Before calling one, briefly tell the user what you are about to check. After it
finishes, interpret the result and continue the investigation. Do not write visual
markers or component syntax; the runtime inserts the visual at the tool position.
"""
    if project_settings.TOOLS_USE_MOCK_DATA
    else ""
)

_SIMULATED_DIAGNOSTIC_TOOLS: list[Tool] = (
    [cast(Tool, ping), cast(Tool, traceroute), cast(Tool, latency_chart)]
    if project_settings.TOOLS_USE_MOCK_DATA
    else []
)

ORCHESTRATOR_SYSTEM_PROMPT = f"""
You are the Lead Network Infrastructure Orchestrator in a multi-agent system.

Your expertise is not only limited to Network Infrastructure and Operations, you can also answer generic questions directly without delegating to specialists.

Your responsibilities:
1. Determine whether the request should be answered directly or delegated.
2. If request needs to be delegated, understand user intent and break the request into a short execution plan.
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

{_SIMULATED_DIAGNOSTIC_PROMPT}

Routing policy:
- If the question is generic or non-network related, answer directly from your knowledge.
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
        *_SIMULATED_DIAGNOSTIC_TOOLS,
    ],
    max_agent_steps=10,
)
