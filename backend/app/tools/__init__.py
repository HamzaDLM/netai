from typing import cast

from haystack.tools import Tool, Toolset

from app.tools.zabbix import (
    get_host_interfaces,
    get_host_inventory,
    get_host_metrics,
    get_host_status,
    get_known_fake_devices,
    get_problem_summary,
    get_trigger_events,
    list_zabbix_hosts,
)

zabbix_tools: list[Tool] = [
    cast(Tool, list_zabbix_hosts),
    cast(Tool, get_known_fake_devices),
    cast(Tool, get_host_status),
    cast(Tool, get_host_inventory),
    cast(Tool, get_host_interfaces),
    cast(Tool, get_host_metrics),
    cast(Tool, get_trigger_events),
    cast(Tool, get_problem_summary),
]

zabbix_toolset = Toolset(zabbix_tools)
