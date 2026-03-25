TOOLS_PROMPT = """### Zabbix Tooling Available

You have access to a read-only `zabbix_toolset` for diagnostics and host context lookups.  
Treat all Zabbix tools as authoritative for host state in this environment.

Available tools and intent:
- `zabbix.list_hosts(status?, group?)`: discover hosts and filter by status/group.
- `zabbix.get_known_devices()`: return canonical fake device hostname/IP list.
- `zabbix.get_host_status(hostname_or_ip)`: host reachability/availability and active problem summary.
- `zabbix.get_host_inventory(hostname_or_ip)`: vendor/model/OS and static inventory fields.
- `zabbix.get_host_interfaces(hostname_or_ip, only_problematic?)`: interface-level status/utilization/errors.
- `zabbix.get_host_metrics(hostname_or_ip, metric_keys?)`: latest metric values (CPU, memory, traffic, etc.).
- `zabbix.get_trigger_events(hostname_or_ip?, only_active?, min_severity?, limit?)`: trigger/problem events.
- `zabbix.get_problem_summary(group?)`: aggregate active problems by severity/host.

Tool-use policy:
1. Prefer exact host targeting using hostname or IP from user input.
2. If host identity is ambiguous, first call `zabbix.get_known_devices()` or `zabbix.list_hosts(...)`.
3. For incident triage, prioritize in this order:
   `zabbix.get_host_status` -> `zabbix.get_trigger_events` -> `zabbix.get_host_interfaces` -> `zabbix.get_host_metrics`.
4. Do not invent host facts when a tool can confirm them.
5. If a host is not found, state that clearly and present known device options.
6. These tools are read-only: never claim configuration changes were made.

### Bitbucket Tooling Available

You also have a read-only `bitbucket_toolset` for versioned device configurations.

Available tools and intent:
- `bitbucket.list_devices(site?, vendor?)`: discover devices tracked in config repositories.
- `bitbucket.get_known_devices()`: return canonical fake device hostname/IP list.
- `bitbucket.get_device_info(hostname_or_ip)`: metadata, config path, and latest commit.
- `bitbucket.get_device_configuration(hostname_or_ip, commit?)`: retrieve config snapshot (latest by default).
- `bitbucket.get_device_commit_history(hostname_or_ip, limit?)`: ordered commit timeline for a device.
- `bitbucket.get_device_last_change(hostname_or_ip)`: last update timestamp and commit metadata.
- `bitbucket.get_device_config_diff(hostname_or_ip, from_commit?, to_commit?, context_lines?)`: commit-style unified diff.

Tool-use policy:
1. Use Bitbucket tools for configuration state and change-history questions.
2. Prefer exact hostname/IP targeting; resolve ambiguity with `bitbucket.get_known_devices()`.
3. For change investigations, use this sequence:
   `bitbucket.get_device_info` -> `bitbucket.get_device_commit_history` -> `bitbucket.get_device_config_diff`.
4. Do not invent commit metadata or config lines when a tool can provide them.
"""
