from haystack.components.agents import Agent

from app.agents.bitbucket_agent import bitbucket_specialist_tool
from app.agents.datamodel_agent import datamodel_specialist_tool
from app.agents.security_agent import security_specialist_tool
from app.agents.servicenow_agent import servicenow_specialist_tool
from app.agents.suzieq_agent import suzieq_specialist_tool
from app.agents.zabbix_agent import zabbix_specialist_tool
from app.llm import llm

SPECIALIST_DESCRIPTIONS: dict[str, str] = {
    "zabbix": "Monitoring and telemetry from Zabbix hosts/triggers/events.",
    "suzieq": "Live network-state and protocol analysis from SuzieQ datasets.",
    "bitbucket": "Repository-backed configuration and change-history analysis.",
    "servicenow": "Operational process and CMDB context from ServiceNow records.",
    "datamodel": "Static infrastructure topology and neighbor relationship analysis.",
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
- security_specialist: {SPECIALIST_DESCRIPTIONS["security"]}

Routing policy:
- Prefer the most specific specialist first.
- Use network_specialist when intent spans multiple domains or confidence is low.
- Never invent tool outputs; only use delegated results as evidence.
"""

orchestrator_agent = Agent(
    chat_generator=llm,
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    tools=[
        zabbix_specialist_tool,
        suzieq_specialist_tool,
        bitbucket_specialist_tool,
        servicenow_specialist_tool,
        datamodel_specialist_tool,
        security_specialist_tool,
    ],
)

# _ROUTE_KEYWORDS: dict[str, set[str]] = {
#     "zabbix": {"zabbix", "trigger", "problem event", "host status", "monitoring"},
#     "suzieq": {
#         "suzieq",
#         "bgp",
#         "ospf",
#         "lldp",
#         "route",
#         "arp",
#         "mac table",
#         "path",
#     },
#     "bitbucket": {
#         "bitbucket",
#         "repo",
#         "repository",
#         "commit",
#         "pull request",
#         "branch",
#     },
#     "servicenow": {"servicenow", "incident", "change request", "problem", "cmdb", "ci"},
#     "datamodel": {"topology", "neighbor", "datamodel", "device inventory", "link"},
# }


# def _extract_latest_user_question(messages: list[Any]) -> str:
#     for message in reversed(messages):
#         role = getattr(message, "role", None)
#         text = getattr(message, "text", None)
#         if isinstance(text, str) and text.strip():
#             if role is None or str(role).lower().endswith("user"):
#                 return text.strip()
#     return ""


# def select_specialist_name(messages: list[Any]) -> str:
#     question = _extract_latest_user_question(messages).lower()
#     if not question:
#         return "network"

#     scores = {name: 0 for name in _ROUTE_KEYWORDS}
#     for name, keywords in _ROUTE_KEYWORDS.items():
#         for keyword in keywords:
#             if keyword in question:
#                 scores[name] += 1

#     selected, score = max(scores.items(), key=lambda item: item[1])
#     if score == 0:
#         return "network"
#     return selected


# def run_orchestrated(messages: list[Any]) -> tuple[str, Any]:
#     selected = select_specialist_name(messages)
#     if selected == "zabbix":
#         return selected, zabbix_agent.run(messages=messages)
#     if selected == "suzieq":
#         return selected, suzieq_agent.run(messages=messages)
#     if selected == "bitbucket":
#         return selected, bitbucket_agent.run(messages=messages)
#     if selected == "servicenow":
#         return selected, servicenow_agent.run(messages=messages)
#     if selected == "datamodel":
#         return selected, datamodel_agent.run(messages=messages)
#     return "network", network_agent.run(messages=messages)
