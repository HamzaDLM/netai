from typing import cast

from haystack.tools import Tool, Toolset

from app.tools.bitbucket_tools import (
    clone_bitbucket_repo,
    get_bitbucket_device_configuration,
    get_bitbucket_device_file_info,
    get_bitbucket_recent_commits,
    list_bitbucket_devices,
)
from app.tools.datamodel_tools import (
    get_device as get_datamodel_device,
    get_known_fake_devices as get_known_fake_datamodel_devices,
    get_neighbors,
    get_topology,
    list_devices as list_datamodel_devices,
    list_links,
)
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

from app.tools.suzieq_tools import (
    check_control_plane_health,
    get_arp_nd,
    get_bgp_sessions,
    get_devices,
    get_interfaces,
    get_lldp_neighbors,
    get_mac_table,
    get_ospf_neighbors,
    get_path,
    get_routes,
    infrastructure_summary,
    list_namespaces,
)
from app.tools.zabbix_tools import (
    get_host_interfaces,
    get_host_inventory,
    get_host_metrics,
    get_host_status,
    get_known_fake_devices as get_known_fake_zabbix_devices,
    get_problem_summary,
    get_trigger_events,
    list_zabbix_hosts,
)

bitbucket_tools: list[Tool] = [
    cast(Tool, clone_bitbucket_repo),
    cast(Tool, list_bitbucket_devices),
    cast(Tool, get_bitbucket_device_file_info),
    cast(Tool, get_bitbucket_device_configuration),
    cast(Tool, get_bitbucket_recent_commits),
]

bitbucket_toolset = Toolset(bitbucket_tools)

datamodel_tools: list[Tool] = [
    cast(Tool, get_known_fake_datamodel_devices),
    cast(Tool, list_datamodel_devices),
    cast(Tool, get_datamodel_device),
    cast(Tool, list_links),
    cast(Tool, get_neighbors),
    cast(Tool, get_topology),
]

datamodel_toolset = Toolset(datamodel_tools)

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

servicenow_toolset = Toolset(servicenow_tools)

suzieq_tools: list[Tool] = [
    cast(Tool, list_namespaces),
    cast(Tool, get_devices),
    cast(Tool, get_interfaces),
    cast(Tool, get_lldp_neighbors),
    cast(Tool, get_bgp_sessions),
    cast(Tool, get_ospf_neighbors),
    cast(Tool, get_routes),
    cast(Tool, get_arp_nd),
    cast(Tool, get_mac_table),
    cast(Tool, get_path),
    cast(Tool, infrastructure_summary),
    cast(Tool, check_control_plane_health),
]

suzieq_toolset = Toolset(suzieq_tools)

zabbix_tools: list[Tool] = [
    cast(Tool, list_zabbix_hosts),
    cast(Tool, get_known_fake_zabbix_devices),
    cast(Tool, get_host_status),
    cast(Tool, get_host_inventory),
    cast(Tool, get_host_interfaces),
    cast(Tool, get_host_metrics),
    cast(Tool, get_trigger_events),
    cast(Tool, get_problem_summary),
]

zabbix_toolset = Toolset(zabbix_tools)
