from typing import cast

from haystack.tools import Tool, Toolset

from app.tools.bitbucket import (
    get_device_commit_history,
    get_device_config_diff,
    get_device_configuration,
    get_device_info,
    get_device_last_change,
    get_known_fake_devices as get_known_fake_bitbucket_devices,
    list_bitbucket_devices,
)
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

bitbucket_tools: list[Tool] = [
    cast(Tool, list_bitbucket_devices),
    cast(Tool, get_known_fake_bitbucket_devices),
    cast(Tool, get_device_info),
    cast(Tool, get_device_configuration),
    cast(Tool, get_device_commit_history),
    cast(Tool, get_device_last_change),
    cast(Tool, get_device_config_diff),
]

bitbucket_toolset = Toolset(bitbucket_tools)
