from datetime import UTC, datetime
from typing import Annotated, Any

from haystack.tools import tool

from app.core.config import project_settings

try:
    from pyzabbix import ZabbixAPI  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    ZabbixAPI = None  # type: ignore


SEVERITY_NUM_TO_NAME = {
    "0": "not_classified",
    "1": "information",
    "2": "warning",
    "3": "average",
    "4": "high",
    "5": "disaster",
}
SEVERITY_NAME_TO_NUM = {
    severity_name: int(severity_number)
    for severity_number, severity_name in SEVERITY_NUM_TO_NAME.items()
}
AVAILABILITY_MAP = {"0": "unknown", "1": "available", "2": "unavailable"}
IFACE_TYPE_MAP = {"1": "agent", "2": "snmp", "3": "ipmi", "4": "jmx"}


class ZabbixToolError(RuntimeError):
    pass


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def to_iso(ts: str | int | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC).isoformat()
    except (TypeError, ValueError):
        return ""


class ZabbixGateway:
    """Small readable wrapper around pyzabbix for our tooling needs."""

    def __init__(self) -> None:
        if not project_settings.ZABBIX_ENABLED:
            raise ZabbixToolError("zabbix_disabled")
        if ZabbixAPI is None:
            raise ZabbixToolError("pyzabbix_not_installed")
        if not project_settings.ZABBIX_API_URL:
            raise ZabbixToolError("missing_zabbix_api_url")
        if not project_settings.ZABBIX_API_TOKEN:
            raise ZabbixToolError("missing_zabbix_api_token")

        self.api = ZabbixAPI(project_settings.ZABBIX_API_URL)
        self.api.timeout = project_settings.ZABBIX_TIMEOUT_SECONDS
        self._login_with_token(project_settings.ZABBIX_API_TOKEN)

    def _login_with_token(self, token: str) -> None:
        # Keep compatibility across pyzabbix versions.
        try:
            self.api.login(api_token=token)
            return
        except TypeError:
            pass
        try:
            self.api.login(api_token=token)
            return
        except TypeError:
            pass
        try:
            self.api.login(user=token, password="")
            return
        except Exception as exc:
            raise ZabbixToolError(f"zabbix_auth_failed:{exc}") from exc

    def api_version(self) -> str:
        try:
            return str(self.api.apiinfo.version())
        except Exception as exc:
            raise ZabbixToolError(f"zabbix_apiinfo_failed:{exc}") from exc

    def list_hosts_raw(self, group: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "output": [
                "hostid",
                "host",
                "name",
                "status",
                "maintenance_status",
                "maintenanceid",
                "available",
                "snmp_available",
                "ipmi_available",
                "jmx_available",
                "active_available",
            ],
            "selectHostGroups": ["groupid", "name"],
            "selectInterfaces": [
                "interfaceid",
                "ip",
                "dns",
                "type",
                "available",
                "error",
                "main",
            ],
            "selectTags": ["tag", "value"],
        }
        if group:
            params["search"] = {"name": group}
            params["searchByAny"] = True
        try:
            return list(self.api.host.get(**params) or [])
        except Exception as exc:
            raise ZabbixToolError(f"host_get_failed:{exc}") from exc

    def known_devices(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for host in self.list_hosts_raw():
            brief = host_brief(host)
            devices.append(
                {
                    "hostname": brief["hostname"],
                    "ip": brief["ip"],
                    "site": brief["site"],
                }
            )
        return devices

    def resolve_host(self, hostname_or_ip: str) -> dict[str, Any] | None:
        target = hostname_or_ip.strip()
        if not target:
            return None

        candidates: list[list[dict[str, Any]]] = []
        try:
            candidates.append(
                list(
                    self.api.host.get(
                        output="extend",
                        selectHostGroups="extend",
                        selectInterfaces="extend",
                        selectTags="extend",
                        filter={"host": [target]},
                    )
                    or []
                )
            )
            candidates.append(
                list(
                    self.api.host.get(
                        output="extend",
                        selectHostGroups="extend",
                        selectInterfaces="extend",
                        selectTags="extend",
                        filter={"name": [target]},
                    )
                    or []
                )
            )
            candidates.append(
                list(
                    self.api.host.get(
                        output="extend",
                        selectHostGroups="extend",
                        selectInterfaces="extend",
                        selectTags="extend",
                        search={"ip": target},
                        searchByAny=True,
                    )
                    or []
                )
            )
        except Exception as exc:
            raise ZabbixToolError(f"host_lookup_failed:{exc}") from exc

        for batch in candidates:
            if batch:
                return batch[0]

        # readable fuzzy fallback
        lookup = normalize(target)
        try:
            fuzzy = list(
                self.api.host.get(
                    output="extend",
                    selectHostGroups="extend",
                    selectInterfaces="extend",
                    selectTags="extend",
                    search={"host": target, "name": target},
                    searchByAny=True,
                )
                or []
            )
        except Exception as exc:
            raise ZabbixToolError(f"host_lookup_failed:{exc}") from exc

        for host in fuzzy:
            text = f"{host.get('host', '')} {host.get('name', '')} {primary_ip(host)}".lower()
            if lookup in text:
                return host
        return None


def primary_ip(host: dict[str, Any]) -> str:
    interfaces = host.get("interfaces") or []
    for iface in interfaces:
        if str(iface.get("main", "0")) == "1":
            ip = str(iface.get("ip") or "")
            if ip:
                return ip
    for iface in interfaces:
        ip = str(iface.get("ip") or "")
        if ip:
            return ip
    return ""


def host_site(host: dict[str, Any]) -> str:
    groups = host.get("hostgroups") or []
    if not groups:
        return ""
    return str(groups[0].get("name", ""))


def host_brief(host: dict[str, Any]) -> dict[str, Any]:
    tags = {
        str(tag_entry.get("tag", "")): str(tag_entry.get("value", ""))
        for tag_entry in (host.get("tags") or [])
    }
    groups = [
        str(host_group.get("name", ""))
        for host_group in (host.get("hostgroups") or [])
        if host_group.get("name")
    ]

    maintenance = (
        str(host.get("maintenance_status", "0")) != "0"
        or str(host.get("maintenanceid", "0")) != "0"
    )
    if maintenance:
        status = "maintenance"
    else:
        # status=0 means monitored/enabled. Availability fields provide runtime hint.
        available_states = [
            str(host.get("available", "0")),
            str(host.get("snmp_available", "0")),
            str(host.get("ipmi_available", "0")),
            str(host.get("jmx_available", "0")),
            str(host.get("active_available", "0")),
        ]
        if str(host.get("status", "1")) != "0":
            status = "down"
        elif "1" in available_states:
            status = "up"
        elif "2" in available_states:
            status = "down"
        else:
            status = "up"

    return {
        "hostid": str(host.get("hostid", "")),
        "hostname": str(host.get("host", "")),
        "display_name": str(host.get("name") or host.get("host") or ""),
        "ip": primary_ip(host),
        "site": host_site(host),
        "status": status,
        "maintenance": maintenance,
        "groups": groups,
        "tags": tags,
    }


def error_payload(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


def gateway() -> ZabbixGateway:
    zabbix_gateway = ZabbixGateway()
    api_version = (
        zabbix_gateway.api_version()
    )  # API probe (latest server can be discovered by version)
    if not api_version:
        raise ZabbixToolError("zabbix_api_version_empty")
    return zabbix_gateway


@tool(name="zabbix.list_hosts")  # type: ignore[operator]
def list_zabbix_hosts(
    status: Annotated[str | None, "Optional status filter: up/down/maintenance"] = None,
    group: Annotated[
        str | None, "Optional group filter (example: Switches, Firewalls)"
    ] = None,
) -> dict[str, Any]:
    """List Zabbix hosts with optional status/group filters."""
    try:
        zabbix_gateway = gateway()
        hosts = [
            host_brief(host_entry)
            for host_entry in zabbix_gateway.list_hosts_raw(group=group)
        ]
        status_lc = normalize(status)
        if status_lc:
            hosts = [
                host_entry
                for host_entry in hosts
                if normalize(str(host_entry.get("status"))) == status_lc
            ]
        return {"count": len(hosts), "hosts": hosts}
    except Exception as exc:
        return error_payload("list_hosts", exc)


@tool(name="zabbix.get_known_devices")  # type: ignore[operator]
def get_known_devices() -> list[dict[str, Any]] | dict[str, Any]:
    """Return discovered hostnames/IPs from Zabbix."""
    try:
        return gateway().known_devices()
    except Exception as exc:
        return error_payload("get_known_devices", exc)


@tool(name="zabbix.get_host_status")  # type: ignore[operator]
def get_host_status(
    hostname_or_ip: Annotated[
        str,
        "Target device hostname or IP, e.g. edge-fw-par-01 or 10.10.1.1",
    ],
) -> dict[str, Any]:
    """Get host status summary including availability and active problems."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": zabbix_gateway.known_devices(),
            }

        problems = list(
            zabbix_gateway.api.problem.get(
                output=["eventid", "severity"],
                hostids=[host["hostid"]],
                sortfield=["eventid"],
                sortorder="DESC",
                limit=200,
            )
            or []
        )

        highest = "information"
        if problems:
            sev_num = max(
                int(problem_entry.get("severity", 1)) for problem_entry in problems
            )
            highest = SEVERITY_NUM_TO_NAME.get(str(sev_num), "information")

        return {
            **host_brief(host),
            "availability": {
                "agent": AVAILABILITY_MAP.get(
                    str(host.get("available", "0")), "unknown"
                ),
                "snmp": AVAILABILITY_MAP.get(
                    str(host.get("snmp_available", "0")), "unknown"
                ),
                "ipmi": AVAILABILITY_MAP.get(
                    str(host.get("ipmi_available", "0")), "unknown"
                ),
                "jmx": AVAILABILITY_MAP.get(
                    str(host.get("jmx_available", "0")), "unknown"
                ),
                "active": AVAILABILITY_MAP.get(
                    str(host.get("active_available", "0")), "unknown"
                ),
            },
            "active_problem_count": len(problems),
            "highest_active_severity": highest,
        }
    except Exception as exc:
        return error_payload("get_host_status", exc)


@tool(name="zabbix.get_host_inventory")  # type: ignore[operator]
def get_host_inventory(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Get host inventory details."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": zabbix_gateway.known_devices(),
            }

        full = list(
            zabbix_gateway.api.host.get(
                output="extend",
                hostids=[host["hostid"]],
                selectInventory="extend",
                selectTags="extend",
                selectHostGroups="extend",
                selectInterfaces="extend",
            )
            or []
        )
        if not full:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": zabbix_gateway.known_devices(),
            }

        resolved = full[0]
        inventory = resolved.get("inventory") or {}
        return {
            **host_brief(resolved),
            "vendor": inventory.get("vendor") or "",
            "model": inventory.get("model") or inventory.get("type") or "",
            "os": inventory.get("os") or "",
            "inventory": inventory,
        }
    except Exception as exc:
        return error_payload("get_host_inventory", exc)


@tool(name="zabbix.get_host_interfaces")  # type: ignore[operator]
def get_host_interfaces(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    only_problematic: Annotated[
        bool,
        "If true, return only unavailable interfaces or ones with reported errors.",
    ] = False,
) -> dict[str, Any]:
    """Return interface status details for a host."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": zabbix_gateway.known_devices(),
            }

        interfaces = list(
            zabbix_gateway.api.hostinterface.get(
                output=[
                    "interfaceid",
                    "hostid",
                    "ip",
                    "dns",
                    "port",
                    "main",
                    "type",
                    "useip",
                    "available",
                    "error",
                ],
                hostids=[host["hostid"]],
            )
            or []
        )

        rows: list[dict[str, Any]] = []
        for iface in interfaces:
            row = {
                "interfaceid": str(iface.get("interfaceid", "")),
                "name": str(
                    iface.get("dns")
                    or iface.get("ip")
                    or iface.get("interfaceid")
                    or ""
                ),
                "type": IFACE_TYPE_MAP.get(str(iface.get("type", "")), "unknown"),
                "admin_status": "up",
                "oper_status": (
                    "up" if str(iface.get("available", "0")) == "1" else "down"
                ),
                "ip": str(iface.get("ip", "")),
                "dns": str(iface.get("dns", "")),
                "port": str(iface.get("port", "")),
                "main": str(iface.get("main", "0")) == "1",
                "error": str(iface.get("error", "")),
            }
            if (
                not only_problematic
                or row["oper_status"] == "down"
                or bool(row["error"])
            ):
                rows.append(row)

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "interfaces": rows,
        }
    except Exception as exc:
        return error_payload("get_host_interfaces", exc)


@tool(name="zabbix.get_host_metrics")  # type: ignore[operator]
def get_host_metrics(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    metric_keys: Annotated[
        list[str] | None,
        "Optional metric keys to fetch. If omitted, returns latest items.",
    ] = None,
) -> dict[str, Any]:
    """Get latest metric values from Zabbix item.lastvalue."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return {
                "error": f"host_not_found:{hostname_or_ip}",
                "known_devices": zabbix_gateway.known_devices(),
            }

        params: dict[str, Any] = {
            "output": [
                "itemid",
                "hostid",
                "name",
                "key_",
                "lastvalue",
                "units",
                "lastclock",
                "state",
                "status",
            ],
            "hostids": [host["hostid"]],
            "sortfield": ["name"],
            "limit": 500,
        }
        if metric_keys:
            params["filter"] = {"key_": metric_keys}

        items = list(zabbix_gateway.api.item.get(**params) or [])
        metrics: dict[str, Any] = {}
        for item in items:
            key = str(item.get("key_", ""))
            if not key:
                continue
            metrics[key] = {
                "name": str(item.get("name", "")),
                "value": item.get("lastvalue", ""),
                "unit": str(item.get("units", "")),
                "last_clock": to_iso(item.get("lastclock")),
                "itemid": str(item.get("itemid", "")),
            }

        payload: dict[str, Any] = {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "metrics": metrics,
        }
        if metric_keys:
            payload["missing_metric_keys"] = [
                metric_key for metric_key in metric_keys if metric_key not in metrics
            ]
        return payload
    except Exception as exc:
        return error_payload("get_host_metrics", exc)


@tool(name="zabbix.get_trigger_events")  # type: ignore[operator]
def get_trigger_events(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP. If omitted, search across all hosts.",
    ] = None,
    only_active: Annotated[bool, "If true, include only active trigger events"] = True,
    min_severity: Annotated[
        str | None,
        "Optional minimum severity: information/warning/average/high/disaster",
    ] = None,
    limit: Annotated[int, "Maximum number of events to return"] = 20,
) -> dict[str, Any]:
    """Return trigger problem events from Zabbix."""
    try:
        if limit < 1:
            return {"error": "limit_must_be_positive"}

        zabbix_gateway = gateway()
        hostids: list[str] = []
        if hostname_or_ip:
            host = zabbix_gateway.resolve_host(hostname_or_ip)
            if not host:
                return {
                    "error": f"host_not_found:{hostname_or_ip}",
                    "known_devices": zabbix_gateway.known_devices(),
                }
            hostids = [str(host["hostid"])]

        params: dict[str, Any] = {
            "output": [
                "eventid",
                "name",
                "severity",
                "clock",
                "acknowledged",
                "r_eventid",
            ],
            "selectHosts": ["host", "name"],
            "recent": not only_active,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            "limit": int(limit),
        }
        if hostids:
            params["hostids"] = hostids
        sev_lc = normalize(min_severity)
        if sev_lc in SEVERITY_NAME_TO_NUM:
            params["severities"] = list(range(SEVERITY_NAME_TO_NUM[sev_lc], 6))

        raw_events = list(zabbix_gateway.api.problem.get(**params) or [])
        events: list[dict[str, Any]] = []
        for event in raw_events:
            hosts = event.get("hosts") or []
            host = hosts[0] if hosts else {}
            is_active = str(event.get("r_eventid", "0")) == "0"
            if only_active and not is_active:
                continue
            events.append(
                {
                    "eventid": str(event.get("eventid", "")),
                    "hostname": str(host.get("host", "")),
                    "name": str(event.get("name", "")),
                    "severity": SEVERITY_NUM_TO_NAME.get(
                        str(event.get("severity", "0")), "not_classified"
                    ),
                    "status": "active" if is_active else "resolved",
                    "since": to_iso(event.get("clock")),
                    "acknowledged": str(event.get("acknowledged", "0")) == "1",
                }
            )

        return {"count": len(events), "events": events[:limit]}
    except Exception as exc:
        return error_payload("get_trigger_events", exc)


@tool(name="zabbix.get_problem_summary")  # type: ignore[operator]
def get_problem_summary(
    group: Annotated[str | None, "Optional group filter"] = None,
) -> dict[str, Any]:
    """Provide active problem summary by severity and host."""
    try:
        zabbix_gateway = gateway()
        hosts = zabbix_gateway.list_hosts_raw(group=group)
        hostids = [
            str(host_entry.get("hostid", ""))
            for host_entry in hosts
            if host_entry.get("hostid")
        ]
        if not hostids:
            return {
                "scope": group if group else "all_hosts",
                "active_problem_total": 0,
                "active_by_severity": {
                    severity_name: 0 for severity_name in SEVERITY_NAME_TO_NUM
                },
                "active_by_host": {},
            }

        problems = list(
            zabbix_gateway.api.problem.get(
                output=["eventid", "severity"],
                selectHosts=["host"],
                hostids=hostids,
                limit=2000,
            )
            or []
        )

        severity_totals = {severity_name: 0 for severity_name in SEVERITY_NAME_TO_NUM}
        host_totals: dict[str, int] = {}

        for event in problems:
            sev = SEVERITY_NUM_TO_NAME.get(
                str(event.get("severity", "0")), "not_classified"
            )
            if sev not in severity_totals:
                severity_totals[sev] = 0
            severity_totals[sev] += 1

            hosts_for_event = event.get("hosts") or []
            if hosts_for_event:
                hostname = str(hosts_for_event[0].get("host", ""))
                host_totals[hostname] = host_totals.get(hostname, 0) + 1

        return {
            "scope": group if group else "all_hosts",
            "active_problem_total": len(problems),
            "active_by_severity": severity_totals,
            "active_by_host": host_totals,
        }
    except Exception as exc:
        return error_payload("get_problem_summary", exc)
