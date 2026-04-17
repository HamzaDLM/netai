from typing import cast

from haystack.components.agents import Agent
from haystack.tools import ComponentTool, Tool

from app.core.config import project_settings
from app.llm import llm

if project_settings.TOOLS_USE_MOCK_DATA:
    from app.tools._zabbix_tools_mock import (
        diagnose_host,
        get_audit_log,
        get_dashboard_snapshot,
        get_events,
        get_host_details,
        get_host_groups,
        get_host_interfaces,
        get_host_metrics_summary,
        get_host_problems,
        get_host_templates,
        get_hosts,
        get_hosts_in_group,
        get_latest_metrics_data,
        get_maintenance,
        get_metrics_history,
        get_problems,
        get_proxies,
        get_recent_problems,
        get_trigger_details,
        get_trigger_problems,
        get_triggers,
        get_zabbix_server_status,
    )
else:
    from app.tools.zabbix_tools import (
        diagnose_host,
        get_audit_log,
        get_dashboard_snapshot,
        get_events,
        get_host_details,
        get_host_groups,
        get_host_interfaces,
        get_host_metrics_summary,
        get_host_problems,
        get_host_templates,
        get_hosts,
        get_hosts_in_group,
        get_latest_metrics_data,
        get_maintenance,
        get_metrics_history,
        get_problems,
        get_proxies,
        get_recent_problems,
        get_trigger_details,
        get_trigger_problems,
        get_triggers,
        get_zabbix_server_status,
    )

ZABBIX_SPECIALIST_PROMPT = """
You are a Zabbix specialist agent for network diagnostics.

Capabilities you can use:
- Host discovery/context: get_hosts, get_host_details, get_host_groups, get_hosts_in_group.
- Problems/alerts: get_problems, get_recent_problems, get_host_problems, get_trigger_problems.
- Triggers/root cause: get_triggers, get_trigger_details.
- Metrics/trends: get_latest_metrics_data, get_metrics_history, get_host_metrics_summary.
- Events/history: get_events, get_audit_log.
- Infra context: get_host_interfaces, get_host_templates, get_maintenance, get_proxies, get_zabbix_server_status.
- AI-friendly summaries: diagnose_host, get_dashboard_snapshot.

Before calling tools, create a short execution plan (1-3 bullets) based on user intent.
Then run the minimum set of tools needed to answer with evidence.
Be concise, cite relevant tool evidence, and clearly state unknowns.
"""

zabbix_tools: list[Tool] = [
    cast(Tool, get_hosts),
    cast(Tool, get_host_details),
    cast(Tool, get_host_interfaces),
    cast(Tool, get_host_groups),
    cast(Tool, get_hosts_in_group),
    cast(Tool, get_problems),
    cast(Tool, get_recent_problems),
    cast(Tool, get_host_problems),
    cast(Tool, get_trigger_problems),
    cast(Tool, get_triggers),
    cast(Tool, get_trigger_details),
    cast(Tool, get_latest_metrics_data),
    cast(Tool, get_metrics_history),
    cast(Tool, get_host_metrics_summary),
    cast(Tool, get_events),
    cast(Tool, get_audit_log),
    cast(Tool, get_host_templates),
    cast(Tool, get_maintenance),
    cast(Tool, get_proxies),
    cast(Tool, get_zabbix_server_status),
    cast(Tool, diagnose_host),
    cast(Tool, get_dashboard_snapshot),
]

zabbix_agent = Agent(
    chat_generator=llm,
    system_prompt=ZABBIX_SPECIALIST_PROMPT,
    tools=zabbix_tools,
    max_agent_steps=10,
)

zabbix_specialist_tool = ComponentTool(
    component=zabbix_agent,
    name="zabbix_specialist",
    description=(
        "Monitoring diagnostics specialist. Use for host discovery, alerts/problems, "
        "triggers/root cause, metrics/history, maintenance/proxy status, and "
        "one-shot host diagnosis from Zabbix."
    ),
    outputs_to_string={"source": "last_message"},
)
