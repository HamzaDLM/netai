# DEPRECATED! DONT TOUCHE
TOOLS_PROMPT = """### Zabbix Tooling Available

You have access to a read-only `zabbix_toolset` for diagnostics and host context lookups.  
Treat all Zabbix tools as authoritative for host state in this environment.

Available tools and intent:
- `zabbix_get_hosts(name?, group?, tags?, status?, maintenance?, limit?)`: host inventory/discovery with rich filters.
- `zabbix_get_host_details(hostname_or_ip)`: complete host details (inventory, interfaces, templates, macros, tags).
- `zabbix_get_host_interfaces(hostname_or_ip, only_problematic?)`: interface-level status and errors.
- `zabbix_get_host_groups()`: host-group catalog with member counts.
- `zabbix_get_hosts_in_group(group, limit?)`: hosts scoped to one group.
- `zabbix_get_problems(hostname_or_ip?, group?, min_severity?, hours?, unacknowledged_only?, unsuppressed_only?, limit?)`: active problems with trigger/host context.
- `zabbix_get_recent_problems(hours?, min_severity?, limit?)`: recent problem timeline (active + recently resolved).
- `zabbix_get_host_problems(hostname_or_ip, hours?, min_severity?, unacknowledged_only?, unsuppressed_only?, limit?)`: host-scoped problems.
- `zabbix_get_trigger_problems(trigger, hours?, limit?)`: problems linked to one trigger.
- `zabbix_get_triggers(hostname_or_ip, min_severity?, include_disabled?, limit?)`: trigger state and expressions for a host.
- `zabbix_get_trigger_details(trigger_id)`: full trigger dependencies/tags/recovery details.
- `zabbix_get_latest_metrics_data(hostname_or_ip, key_patterns?, limit?)`: latest item values.
- `zabbix_get_metrics_history(item_id?, item_key?, hostname_or_ip?, hours?, aggregation?, limit?)`: raw/trend metric history.
- `zabbix_get_host_metrics_summary(hostname_or_ip, key_patterns?)`: utilization + item error summary.
- `zabbix_get_events(hostname_or_ip?, problem_event_id?, hours?, include_ok_events?, limit?)`: trigger event timeline.
- `zabbix_get_audit_log(hours?, actor?, action?, limit?)`: recent configuration/administrative changes.
- `zabbix_get_host_templates(hostname_or_ip)`: templates linked to a host.
- `zabbix_get_maintenance(hostname_or_ip?)`: maintenance windows and host maintenance state.
- `zabbix_get_proxies(limit?)`: proxy status and host handling footprint.
- `zabbix_get_zabbix_server_status()`: server/API health and summarized counters.
- `zabbix_diagnose_host(hostname_or_ip, hours?)`: one-shot diagnostics summary.
- `zabbix_get_dashboard_snapshot(dashboard?, hours?, limit?)`: compact dashboard snapshot (`problems`, `hosts`, `overview`).

Tool-use policy:
1. Prefer exact host targeting using hostname or IP from user input.
2. If host identity is ambiguous, start with `zabbix_get_hosts(...)` and narrow to one host.
3. For incident triage, prioritize in this order:
   `zabbix_diagnose_host` -> `zabbix_get_host_problems` -> `zabbix_get_host_interfaces` -> `zabbix_get_host_metrics_summary`.
4. Do not invent host facts when a tool can confirm them.
5. If a host is not found, state that clearly and present known host options.
6. These tools are read-only: never claim configuration changes were made.

### Bitbucket Tooling Available

You also have a read-only `bitbucket_toolset` for versioned device configurations.

Available tools and intent:
- `bitbucket_device_config_exists(device)`: fast existence check for a device config file (no full repo listing).
- `bitbucket_get_device_file_info(device)`: show commit count plus latest commit metadata for a device file.
- `bitbucket_get_recent_device_config_diff(device)`: return latest sanitized unified diff payload for one device file.
- `bitbucket_get_device_configuration(device, commit_ref?)`: retrieve sanitized device configuration at HEAD or a commit.
- `bitbucket_get_recent_commits_for_host(hostname, limit?)`: latest commits affecting one host's device configuration.

Tool-use policy:
1. Use Bitbucket tools for configuration state and change-history questions.
2. Do not enumerate all devices; use `bitbucket_device_config_exists` to validate whether a specific device file exists.
3. For device-level investigations, use:
   `bitbucket_get_device_file_info` -> `bitbucket_get_recent_device_config_diff` (when diff is needed).
4. Use `bitbucket_get_recent_commits_for_host` when the user asks what changed recently for a specific host.
5. Do not invent commit metadata or diff lines when a tool can provide them.

### Datamodel Tooling Available

You also have a read-only `datamodel_toolset` for infrastructure topology mapping.

Available tools and intent:
- `datamodel_get_known_devices()`: canonical datamodel device list.
- `datamodel_list_devices(site?, role?, status?)`: filtered inventory.
- `datamodel_get_device(hostname_or_ip)`: single device details with link counters.
- `datamodel_list_links(site?, status?)`: links with endpoint interfaces and state.
- `datamodel_get_neighbors(hostname_or_ip, only_up?)`: immediate adjacency view for one node.
- `datamodel_get_topology(site?, include_only_link_statuses?)`: graph payload for topology viewers.

Tool-use policy:
1. Use datamodel tools when the user asks for topology, links, adjacency, or mapping.
2. Prefer `datamodel_get_topology(...)` for visualization payloads and edge-coloring workflows.
3. For node drill-down, use:
   `datamodel_get_device` -> `datamodel_get_neighbors`.
4. Keep device/link state factual and sourced from tools.

### ServiceNow Tooling Available

You also have a read-only `servicenow_toolset` for ITSM records and CMDB context.

Available tools and intent:
- `servicenow_get_known_cis()`: canonical CI shortlist for quick disambiguation.
- `servicenow_list_incidents(state?, priority?, assignment_group?, service?, only_major?, limit?)`: incident triage list.
- `servicenow_get_incident(incident_number)`: detailed incident with linked change/problem references.
- `servicenow_list_change_requests(state?, risk?, service?, assignment_group?, limit?)`: change calendar and risk-focused view.
- `servicenow_get_change_request(change_number)`: single change detail payload.
- `servicenow_list_problems(state?, priority?, service?, assignment_group?, limit?)`: problem records and known-error tracking.
- `servicenow_get_problem(problem_number)`: single problem detail payload.
- `servicenow_list_cis(ci_class?, site?, service?, install_status?, query?, limit?)`: CMDB CI discovery.
- `servicenow_get_ci(ci_name_or_sys_id)`: CI detail with open incident/change/problem counters.
- `servicenow_get_service_summary(service)`: aggregate service posture (active incidents/open changes/open problems).

Tool-use policy:
1. Use ServiceNow tools for tickets, change windows, ownership, and record linkage.
2. Resolve ambiguous CI references with `servicenow_get_known_cis()` or `servicenow_list_cis(...)` before deep lookup.
3. For incident impact investigations, use this sequence:
   `servicenow_get_incident` -> linked `servicenow_get_problem`/`servicenow_get_change_request` -> `servicenow_get_ci`.
4. Do not claim ticket updates/closures: these tools are strictly read-only.

### SuzieQ Tooling Available

You also have a read-only `suzieq_toolset` for multi-vendor network state and control-plane visibility.

Available tools and intent:
- `suzieq_list_namespaces()`: enumerate namespaces present in SuzieQ.
- `suzieq_get_devices(namespace?, hostname?)`: inventory and device operational state.
- `suzieq_get_interfaces(namespace?, hostname?, ifname?, state?)`: interface status/counters.
- `suzieq_get_lldp_neighbors(namespace?, hostname?)`: LLDP adjacency for topology validation.
- `suzieq_get_bgp_sessions(namespace?, hostname?, state?)`: BGP neighbor/session health.
- `suzieq_get_ospf_neighbors(namespace?, hostname?, state?)`: OSPF adjacency details.
- `suzieq_get_routes(namespace?, hostname?, prefix?, vrf?)`: route table and next-hop analysis.
- `suzieq_get_arp_nd(namespace?, hostname?, ip_address?)`: ARP/ND lookup visibility.
- `suzieq_get_mac_table(namespace?, hostname?, vlan?, macaddr?)`: L2 forwarding table visibility.
- `suzieq_get_path(namespace, source, destination, vrf?)`: computed forwarding path.
- `suzieq_infrastructure_summary(namespace?)`: broad inventory/protocol summary across domains.
- `suzieq_check_control_plane_health(namespace?)`: protocol-focused assert checks.

Tool-use policy:
1. Use SuzieQ for cross-device operational truth (interfaces/protocol adjacency/routing).
2. If scope is unclear, start with `suzieq_list_namespaces()` then narrow by namespace/hostname.
3. For control-plane incidents, prefer this sequence:
   `suzieq_get_devices` -> `suzieq_get_interfaces` -> `suzieq_get_bgp_sessions`/`suzieq_get_ospf_neighbors` -> `suzieq_get_routes`.
4. Treat these tools as read-only diagnostics and do not claim config changes.
"""
