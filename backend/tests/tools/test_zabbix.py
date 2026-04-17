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


def _invoke_tool(tool_obj, **kwargs):
    if not hasattr(tool_obj, "invoke"):
        raise AssertionError("Expected a tool object with an .invoke method")
    try:
        return tool_obj.invoke(kwargs)
    except TypeError:
        return tool_obj.invoke(**kwargs)


def test_get_hosts_filters_by_group_and_status() -> None:
    payload = _invoke_tool(get_hosts, group="VPN", status="down")

    assert payload["count"] == 1
    assert payload["hosts"][0]["hostname"] == "vpn-gw-lon-01"


def test_get_host_details_and_not_found_shape() -> None:
    payload = _invoke_tool(get_host_details, hostname_or_ip="edge-fw-par-01")
    assert payload["hostname"] == "edge-fw-par-01"
    assert len(payload["templates"]) >= 1
    assert len(payload["macros"]) >= 1

    not_found = _invoke_tool(get_host_details, hostname_or_ip="unknown-host")
    assert not_found["error"] == "host_not_found:unknown-host"
    assert len(not_found["known_hosts"]) >= 1


def test_get_host_groups_and_hosts_in_group() -> None:
    groups = _invoke_tool(get_host_groups)
    assert groups["count"] >= 3

    in_group = _invoke_tool(get_hosts_in_group, group="Firewalls")
    assert in_group["count"] >= 1
    assert any(item["hostname"] == "edge-fw-par-01" for item in in_group["hosts"])


def test_get_host_interfaces_only_problematic() -> None:
    payload = _invoke_tool(
        get_host_interfaces,
        hostname_or_ip="dist-rtr-nyc-01",
        only_problematic=True,
    )

    assert payload["count"] >= 1
    assert all(
        row["oper_status"] != "up" or bool(row["error"])
        for row in payload["interfaces"]
    )


def test_get_problems_defaults_are_signal_focused() -> None:
    payload = _invoke_tool(get_problems)

    assert payload["filters"]["min_severity"] == "average"
    assert payload["filters"]["active_only"] is True
    assert payload["filters"]["unsuppressed_only"] is True
    assert all(row["status"] == "active" for row in payload["problems"])
    assert all(row["suppressed"] is False for row in payload["problems"])
    assert all(
        row["severity"] in {"average", "high", "disaster"}
        for row in payload["problems"]
    )


def test_get_recent_and_host_problems() -> None:
    recent = _invoke_tool(get_recent_problems, hours=24)
    assert any(row["status"] == "resolved" for row in recent["problems"])

    host = _invoke_tool(
        get_host_problems,
        hostname_or_ip="vpn-gw-lon-01",
        min_severity="disaster",
    )
    assert host["count"] >= 1
    assert all(row["severity"] == "disaster" for row in host["problems"])


def test_get_trigger_problems_and_trigger_details() -> None:
    by_trigger = _invoke_tool(get_trigger_problems, trigger="Host unreachable")
    assert by_trigger["count"] >= 1
    trigger_id = by_trigger["trigger"]["triggerid"]

    details = _invoke_tool(get_trigger_details, trigger_id=trigger_id)
    assert details["triggerid"] == trigger_id
    assert len(details["hosts"]) >= 1
    assert len(details["items"]) >= 1


def test_get_triggers_filters_and_payload_shape() -> None:
    payload = _invoke_tool(
        get_triggers,
        hostname_or_ip="vpn-gw-lon-01",
        min_severity="high",
        include_disabled=False,
    )

    assert payload["hostname"] == "vpn-gw-lon-01"
    assert payload["count"] >= 1
    assert all(row["severity"] in {"high", "disaster"} for row in payload["triggers"])


def test_metrics_latest_history_and_summary() -> None:
    latest = _invoke_tool(
        get_latest_metrics_data,
        hostname_or_ip="dist-rtr-nyc-01",
        key_patterns=["*cpu*", "*memory*"],
    )
    assert latest["count"] >= 2
    assert all(
        "cpu" in row["key"] or "memory" in row["key"] for row in latest["metrics"]
    )

    history = _invoke_tool(
        get_metrics_history,
        item_key="cpu.util",
        hostname_or_ip="dist-rtr-nyc-01",
        aggregation="avg",
    )
    assert history["aggregation"] == "avg"
    assert history["count"] >= 1

    summary = _invoke_tool(get_host_metrics_summary, hostname_or_ip="dist-rtr-nyc-01")
    assert summary["summary"]["error_item_count"] >= 1


def test_get_events_filters_and_not_found() -> None:
    payload = _invoke_tool(
        get_events,
        hostname_or_ip="vpn-gw-lon-01",
        include_ok_events=True,
    )
    assert payload["count"] >= 2

    missing = _invoke_tool(get_events, problem_event_id="missing-id")
    assert missing["error"] == "event_not_found:missing-id"


def test_audit_templates_maintenance_proxies_server() -> None:
    audit = _invoke_tool(get_audit_log, actor="automation")
    assert audit["count"] >= 1

    templates = _invoke_tool(get_host_templates, hostname_or_ip="edge-fw-par-01")
    assert templates["count"] >= 1

    maintenance = _invoke_tool(get_maintenance, hostname_or_ip="wlc-sfo-01")
    assert maintenance["count"] >= 1

    proxies = _invoke_tool(get_proxies)
    assert proxies["count"] >= 1

    server = _invoke_tool(get_zabbix_server_status)
    assert "api_version" in server
    assert "inventory" in server


def test_diagnose_host_and_dashboard_snapshot() -> None:
    diag = _invoke_tool(diagnose_host, hostname_or_ip="vpn-gw-lon-01")
    assert diag["hostname"] == "vpn-gw-lon-01"
    assert len(diag["summary"]) > 0

    dash = _invoke_tool(get_dashboard_snapshot, dashboard="overview")
    assert dash["dashboard"] == "overview"
    assert "host_total" in dash["data"]
