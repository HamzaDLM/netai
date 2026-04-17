from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
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
SEVERITY_ORDER = {
    "not_classified": 0,
    "information": 1,
    "warning": 2,
    "average": 3,
    "high": 4,
    "disaster": 5,
}
AVAILABILITY_MAP = {"0": "unknown", "1": "available", "2": "unavailable"}
IFACE_TYPE_MAP = {"1": "agent", "2": "snmp", "3": "ipmi", "4": "jmx"}

DEFAULT_LIMIT = 100
DEFAULT_HOURS = 24
DEFAULT_MIN_SEVERITY = "average"
MAX_LIMIT = 1000


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


def clamp_limit(limit: int | None, default: int = DEFAULT_LIMIT) -> int:
    if limit is None:
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return 1
    return min(value, MAX_LIMIT)


def time_from_hours(hours: int | float | None) -> int:
    try:
        effective_hours = float(hours if hours is not None else DEFAULT_HOURS)
    except (TypeError, ValueError):
        effective_hours = float(DEFAULT_HOURS)
    if effective_hours <= 0:
        effective_hours = float(DEFAULT_HOURS)
    return int((datetime.now(tz=UTC) - timedelta(hours=effective_hours)).timestamp())


def matches_pattern(value: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    value_lc = value.lower()
    for pattern in patterns:
        pattern_lc = pattern.lower().strip()
        if not pattern_lc:
            continue
        if "*" in pattern_lc or "?" in pattern_lc:
            if fnmatch(value_lc, pattern_lc):
                return True
        elif pattern_lc in value_lc:
            return True
    return False


def parse_tags_filter(tags: list[str] | None) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {}
    for raw in tags or []:
        text = (raw or "").strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            parsed[normalize(key)] = value.strip()
        else:
            parsed[normalize(text)] = None
    return parsed


def severity_threshold(min_severity: str | None) -> int:
    sev = normalize(min_severity) or DEFAULT_MIN_SEVERITY
    return SEVERITY_ORDER.get(sev, SEVERITY_ORDER[DEFAULT_MIN_SEVERITY])


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


def host_tags(host: dict[str, Any]) -> dict[str, str]:
    return {
        str(tag_entry.get("tag", "")): str(tag_entry.get("value", ""))
        for tag_entry in (host.get("tags") or [])
    }


def host_groups(host: dict[str, Any]) -> list[str]:
    return [
        str(host_group.get("name", ""))
        for host_group in (host.get("hostgroups") or [])
        if host_group.get("name")
    ]


def host_status(host: dict[str, Any]) -> str:
    maintenance = (
        str(host.get("maintenance_status", "0")) != "0"
        or str(host.get("maintenanceid", "0")) != "0"
    )
    if maintenance:
        return "maintenance"

    available_states = [
        str(host.get("available", "0")),
        str(host.get("snmp_available", "0")),
        str(host.get("ipmi_available", "0")),
        str(host.get("jmx_available", "0")),
        str(host.get("active_available", "0")),
    ]
    if str(host.get("status", "1")) != "0":
        return "down"
    if "1" in available_states:
        return "up"
    if "2" in available_states:
        return "down"
    return "up"


def host_availability(host: dict[str, Any]) -> dict[str, str]:
    return {
        "agent": AVAILABILITY_MAP.get(str(host.get("available", "0")), "unknown"),
        "snmp": AVAILABILITY_MAP.get(str(host.get("snmp_available", "0")), "unknown"),
        "ipmi": AVAILABILITY_MAP.get(str(host.get("ipmi_available", "0")), "unknown"),
        "jmx": AVAILABILITY_MAP.get(str(host.get("jmx_available", "0")), "unknown"),
        "active": AVAILABILITY_MAP.get(
            str(host.get("active_available", "0")), "unknown"
        ),
    }


def host_brief(host: dict[str, Any]) -> dict[str, Any]:
    interfaces = host.get("interfaces") or []
    return {
        "hostid": str(host.get("hostid", "")),
        "hostname": str(host.get("host", "")),
        "display_name": str(host.get("name") or host.get("host") or ""),
        "ip": primary_ip(host),
        "site": host_site(host),
        "status": host_status(host),
        "maintenance": (
            str(host.get("maintenance_status", "0")) != "0"
            or str(host.get("maintenanceid", "0")) != "0"
        ),
        "groups": host_groups(host),
        "tags": host_tags(host),
        "availability": host_availability(host),
        "interfaces": [
            {
                "interfaceid": str(iface.get("interfaceid", "")),
                "ip": str(iface.get("ip", "")),
                "dns": str(iface.get("dns", "")),
                "type": IFACE_TYPE_MAP.get(str(iface.get("type", "")), "unknown"),
                "main": str(iface.get("main", "0")) == "1",
                "status": AVAILABILITY_MAP.get(
                    str(iface.get("available", "0")), "unknown"
                ),
                "error": str(iface.get("error", "")),
            }
            for iface in interfaces
        ],
        "last_seen": to_iso(host.get("lastaccess")),
    }


def error_payload(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


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

    def call_list(self, method_path: str, **params: Any) -> list[dict[str, Any]]:
        target: Any = self.api
        try:
            for part in method_path.split("."):
                target = getattr(target, part)
            result = target(**params)
            return list(result or [])
        except Exception as exc:
            raise ZabbixToolError(f"{method_path}_failed:{exc}") from exc

    def call_count(self, method_path: str, **params: Any) -> int:
        target: Any = self.api
        try:
            for part in method_path.split("."):
                target = getattr(target, part)
            result = target(**params)
            if isinstance(result, str):
                return int(result)
            if isinstance(result, int):
                return result
            return int(result or 0)
        except Exception:
            return 0

    def list_hosts_raw(
        self,
        *,
        groupids: list[str] | None = None,
        hostids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
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
                "lastaccess",
                "proxy_hostid",
            ],
            "selectHostGroups": ["groupid", "name"],
            "selectInterfaces": [
                "interfaceid",
                "ip",
                "dns",
                "port",
                "type",
                "available",
                "error",
                "main",
                "useip",
            ],
            "selectTags": ["tag", "value"],
            "selectParentTemplates": ["templateid", "host", "name"],
            "selectInventory": "extend",
            "selectMacros": ["macro", "value", "description"],
            "sortfield": ["host"],
            "sortorder": "ASC",
        }
        if groupids:
            params["groupids"] = groupids
        if hostids:
            params["hostids"] = hostids
        if limit:
            params["limit"] = clamp_limit(limit)
        return self.call_list("host.get", **params)

    def known_hosts(self, limit: int = 200) -> list[dict[str, Any]]:
        hosts = self.list_hosts_raw(limit=limit)
        return [
            {
                "hostname": str(host.get("host", "")),
                "display_name": str(host.get("name") or host.get("host") or ""),
                "ip": primary_ip(host),
                "site": host_site(host),
            }
            for host in hosts
        ]

    def resolve_host(self, hostname_or_ip: str) -> dict[str, Any] | None:
        target = hostname_or_ip.strip()
        if not target:
            return None

        candidates: list[list[dict[str, Any]]] = []
        candidates.append(
            self.call_list(
                "host.get",
                output="extend",
                selectHostGroups="extend",
                selectInterfaces="extend",
                selectTags="extend",
                selectParentTemplates="extend",
                selectInventory="extend",
                selectMacros="extend",
                filter={"host": [target]},
            )
        )
        candidates.append(
            self.call_list(
                "host.get",
                output="extend",
                selectHostGroups="extend",
                selectInterfaces="extend",
                selectTags="extend",
                selectParentTemplates="extend",
                selectInventory="extend",
                selectMacros="extend",
                filter={"name": [target]},
            )
        )
        candidates.append(
            self.call_list(
                "host.get",
                output="extend",
                selectHostGroups="extend",
                selectInterfaces="extend",
                selectTags="extend",
                selectParentTemplates="extend",
                selectInventory="extend",
                selectMacros="extend",
                search={"ip": target},
                searchByAny=True,
            )
        )

        for batch in candidates:
            if batch:
                return batch[0]

        fuzzy = self.call_list(
            "host.get",
            output="extend",
            selectHostGroups="extend",
            selectInterfaces="extend",
            selectTags="extend",
            selectParentTemplates="extend",
            selectInventory="extend",
            selectMacros="extend",
            search={"host": target, "name": target},
            searchByAny=True,
        )
        lookup = normalize(target)
        for host in fuzzy:
            text = f"{host.get('host', '')} {host.get('name', '')} {primary_ip(host)}".lower()
            if lookup in text:
                return host
        return None


def gateway() -> ZabbixGateway:
    zabbix_gateway = ZabbixGateway()
    api_version = zabbix_gateway.api_version()
    if not api_version:
        raise ZabbixToolError("zabbix_api_version_empty")
    return zabbix_gateway


def host_not_found(
    zabbix_gateway: ZabbixGateway,
    hostname_or_ip: str,
    *,
    tool_name: str,
) -> dict[str, Any]:
    try:
        known_hosts = zabbix_gateway.known_hosts()
    except Exception:
        known_hosts = []
    return {
        "error": f"host_not_found:{hostname_or_ip}",
        "known_hosts": known_hosts,
        "tool": tool_name,
    }


def enrich_trigger_map(
    zabbix_gateway: ZabbixGateway,
    triggerids: list[str],
) -> dict[str, dict[str, Any]]:
    if not triggerids:
        return {}
    rows = zabbix_gateway.call_list(
        "trigger.get",
        output=[
            "triggerid",
            "description",
            "status",
            "priority",
            "lastchange",
            "expression",
            "recovery_expression",
            "state",
            "error",
            "value",
        ],
        selectDependencies=["triggerid", "description"],
        selectHosts=["hostid", "host", "name"],
        selectTags=["tag", "value"],
        triggerids=triggerids,
    )
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        triggerid = str(row.get("triggerid", ""))
        mapped[triggerid] = {
            "triggerid": triggerid,
            "description": str(row.get("description", "")),
            "enabled": str(row.get("status", "0")) == "0",
            "severity": SEVERITY_NUM_TO_NAME.get(
                str(row.get("priority", "0")), "not_classified"
            ),
            "last_change": to_iso(row.get("lastchange")),
            "expression": str(row.get("expression", "")),
            "recovery_expression": str(row.get("recovery_expression", "")),
            "state": str(row.get("state", "")),
            "error": str(row.get("error", "")),
            "value": str(row.get("value", "")),
            "dependencies": [
                {
                    "triggerid": str(dep.get("triggerid", "")),
                    "description": str(dep.get("description", "")),
                }
                for dep in (row.get("dependencies") or [])
            ],
            "hosts": [
                {
                    "hostid": str(host.get("hostid", "")),
                    "host": str(host.get("host", "")),
                    "name": str(host.get("name", "")),
                }
                for host in (row.get("hosts") or [])
            ],
            "tags": [
                {
                    "tag": str(tag.get("tag", "")),
                    "value": str(tag.get("value", "")),
                }
                for tag in (row.get("tags") or [])
            ],
        }
    return mapped


def normalize_problem_row(
    event: dict[str, Any], trigger_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    triggerid = str(event.get("objectid", ""))
    trigger = trigger_map.get(triggerid) or {}
    hosts = trigger.get("hosts") or []
    host = hosts[0] if hosts else {}
    severity = SEVERITY_NUM_TO_NAME.get(
        str(event.get("severity", "0")), "not_classified"
    )
    is_active = str(event.get("r_eventid", "0")) == "0"
    return {
        "eventid": str(event.get("eventid", "")),
        "hostname": str(host.get("host", "")),
        "host_display_name": str(host.get("name", "")),
        "name": str(event.get("name", "")),
        "severity": severity,
        "status": "active" if is_active else "resolved",
        "since": to_iso(event.get("clock")),
        "acknowledged": str(event.get("acknowledged", "0")) == "1",
        "suppressed": str(event.get("suppressed", "0")) == "1",
        "trigger": trigger,
        "last_event": {
            "eventid": str(event.get("eventid", "")),
            "clock": to_iso(event.get("clock")),
        },
    }


def build_problems_payload(
    zabbix_gateway: ZabbixGateway,
    *,
    hostname_or_ip: str | None = None,
    group: str | None = None,
    min_severity: str | None = None,
    hours: int | float | None = DEFAULT_HOURS,
    unacknowledged_only: bool = False,
    unsuppressed_only: bool = True,
    limit: int = DEFAULT_LIMIT,
    active_only: bool = True,
    recent: bool = True,
    host_not_found_tool_name: str = "get_problems",
) -> dict[str, Any]:
    hostids: list[str] = []
    if hostname_or_ip:
        resolved = zabbix_gateway.resolve_host(hostname_or_ip)
        if not resolved:
            return host_not_found(
                zabbix_gateway,
                hostname_or_ip,
                tool_name=host_not_found_tool_name,
            )
        hostids = [str(resolved.get("hostid", ""))]

    groupids: list[str] = []
    if group:
        groups = zabbix_gateway.call_list(
            "hostgroup.get",
            output=["groupid", "name"],
            search={"name": group},
            searchByAny=True,
        )
        groupids = [str(row.get("groupid", "")) for row in groups if row.get("groupid")]

    params: dict[str, Any] = {
        "output": [
            "eventid",
            "name",
            "severity",
            "clock",
            "acknowledged",
            "r_eventid",
            "suppressed",
            "objectid",
        ],
        "selectTags": ["tag", "value"],
        "recent": recent,
        "sortfield": "eventid",
        "sortorder": "DESC",
        "limit": clamp_limit(limit),
        "time_from": time_from_hours(hours),
    }
    if hostids:
        params["hostids"] = hostids
    if groupids:
        params["groupids"] = groupids

    problems = zabbix_gateway.call_list("problem.get", **params)

    threshold = severity_threshold(min_severity)
    filtered: list[dict[str, Any]] = []
    for event in problems:
        sev_name = SEVERITY_NUM_TO_NAME.get(
            str(event.get("severity", "0")), "not_classified"
        )
        if SEVERITY_ORDER.get(sev_name, 0) < threshold:
            continue
        is_active = str(event.get("r_eventid", "0")) == "0"
        if active_only and not is_active:
            continue
        if unacknowledged_only and str(event.get("acknowledged", "0")) == "1":
            continue
        if unsuppressed_only and str(event.get("suppressed", "0")) == "1":
            continue
        filtered.append(event)
    filtered.sort(
        key=lambda event: (
            int(event.get("severity", 0) or 0),
            int(event.get("eventid", 0) or 0),
        ),
        reverse=True,
    )

    triggerids = [
        str(event.get("objectid", ""))
        for event in filtered
        if str(event.get("objectid", ""))
    ]
    trigger_map = enrich_trigger_map(zabbix_gateway, triggerids)

    rows = [normalize_problem_row(event, trigger_map) for event in filtered]
    return {
        "count": len(rows),
        "filters": {
            "hostname_or_ip": hostname_or_ip,
            "group": group,
            "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "unacknowledged_only": unacknowledged_only,
            "unsuppressed_only": unsuppressed_only,
            "active_only": active_only,
        },
        "problems": rows[: clamp_limit(limit)],
    }


@tool(name="zabbix.get_hosts")  # type: ignore[operator]
def get_hosts(
    name: Annotated[str | None, "Optional hostname/display-name filter"] = None,
    group: Annotated[str | None, "Optional host-group filter"] = None,
    tags: Annotated[
        list[str] | None,
        "Optional tag filters as ['key=value', 'role']; all entries must match.",
    ] = None,
    status: Annotated[
        str | None,
        "Optional status filter: up/down/maintenance",
    ] = None,
    maintenance: Annotated[
        bool | None,
        "Optional maintenance filter.",
    ] = None,
    limit: Annotated[int, "Maximum number of hosts to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """List hosts with rich metadata for diagnostics."""
    try:
        zabbix_gateway = gateway()

        groupids: list[str] | None = None
        if group:
            groups = zabbix_gateway.call_list(
                "hostgroup.get",
                output=["groupid", "name"],
                search={"name": group},
                searchByAny=True,
            )
            groupids = [
                str(row.get("groupid", "")) for row in groups if row.get("groupid")
            ]

        hosts = zabbix_gateway.list_hosts_raw(
            groupids=groupids, limit=clamp_limit(limit)
        )

        tag_filter = parse_tags_filter(tags)
        name_lc = normalize(name)
        status_lc = normalize(status)
        rows: list[dict[str, Any]] = []
        for host in hosts:
            brief = host_brief(host)
            haystack = (
                f"{brief['hostname']} {brief['display_name']} {brief['ip']}".lower()
            )
            if name_lc and name_lc not in haystack:
                continue
            if status_lc and normalize(str(brief.get("status"))) != status_lc:
                continue
            if (
                maintenance is not None
                and bool(brief.get("maintenance")) != maintenance
            ):
                continue
            if tag_filter:
                host_tags_map = {normalize(k): str(v) for k, v in brief["tags"].items()}
                failed = False
                for key, expected in tag_filter.items():
                    if key not in host_tags_map:
                        failed = True
                        break
                    if expected is not None and host_tags_map[key] != expected:
                        failed = True
                        break
                if failed:
                    continue
            rows.append(brief)

        return {
            "count": len(rows),
            "filters": {
                "name": name,
                "group": group,
                "tags": tags or [],
                "status": status,
                "maintenance": maintenance,
            },
            "hosts": rows[: clamp_limit(limit)],
        }
    except Exception as exc:
        return error_payload("get_hosts", exc)


@tool(name="zabbix.get_host_details")  # type: ignore[operator]
def get_host_details(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Get full host context: interfaces, inventory, templates, tags, macros."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway, hostname_or_ip, tool_name="get_host_details"
            )

        inventory = host.get("inventory") or {}
        macros = [
            {
                "macro": str(entry.get("macro", "")),
                "value": str(entry.get("value", "")),
                "description": str(entry.get("description", "")),
            }
            for entry in (host.get("macros") or [])
        ]
        templates = [
            {
                "templateid": str(entry.get("templateid", "")),
                "hostname": str(entry.get("host", "")),
                "name": str(entry.get("name", "")),
            }
            for entry in (host.get("parentTemplates") or [])
        ]

        return {
            **host_brief(host),
            "inventory": inventory,
            "vendor": inventory.get("vendor") or "",
            "model": inventory.get("model") or inventory.get("type") or "",
            "os": inventory.get("os") or "",
            "interfaces": [
                {
                    "interfaceid": str(iface.get("interfaceid", "")),
                    "ip": str(iface.get("ip", "")),
                    "dns": str(iface.get("dns", "")),
                    "port": str(iface.get("port", "")),
                    "type": IFACE_TYPE_MAP.get(str(iface.get("type", "")), "unknown"),
                    "use_ip": str(iface.get("useip", "1")) == "1",
                    "main": str(iface.get("main", "0")) == "1",
                    "status": AVAILABILITY_MAP.get(
                        str(iface.get("available", "0")), "unknown"
                    ),
                    "error": str(iface.get("error", "")),
                }
                for iface in (host.get("interfaces") or [])
            ],
            "templates": templates,
            "macros": macros,
        }
    except Exception as exc:
        return error_payload("get_host_details", exc)


@tool(name="zabbix.get_host_interfaces")  # type: ignore[operator]
def get_host_interfaces(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    only_problematic: Annotated[
        bool,
        "If true, include only unavailable interfaces or interfaces with errors.",
    ] = False,
) -> dict[str, Any]:
    """Return host interface status details."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway, hostname_or_ip, tool_name="get_host_interfaces"
            )

        rows: list[dict[str, Any]] = []
        for iface in host.get("interfaces") or []:
            row = {
                "interfaceid": str(iface.get("interfaceid", "")),
                "name": str(
                    iface.get("dns")
                    or iface.get("ip")
                    or iface.get("interfaceid")
                    or ""
                ),
                "type": IFACE_TYPE_MAP.get(str(iface.get("type", "")), "unknown"),
                "ip": str(iface.get("ip", "")),
                "dns": str(iface.get("dns", "")),
                "port": str(iface.get("port", "")),
                "main": str(iface.get("main", "0")) == "1",
                "oper_status": (
                    "up" if str(iface.get("available", "0")) == "1" else "down"
                ),
                "error": str(iface.get("error", "")),
            }
            if only_problematic and row["oper_status"] == "up" and not row["error"]:
                continue
            rows.append(row)

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "count": len(rows),
            "interfaces": rows,
        }
    except Exception as exc:
        return error_payload("get_host_interfaces", exc)


@tool(name="zabbix.get_host_groups")  # type: ignore[operator]
def get_host_groups() -> dict[str, Any]:
    """Return host groups with host counts."""
    try:
        zabbix_gateway = gateway()
        groups = zabbix_gateway.call_list(
            "hostgroup.get",
            output=["groupid", "name"],
            selectHosts=["hostid"],
            sortfield=["name"],
            sortorder="ASC",
        )
        rows = [
            {
                "groupid": str(group.get("groupid", "")),
                "name": str(group.get("name", "")),
                "host_count": len(group.get("hosts") or []),
            }
            for group in groups
        ]
        return {"count": len(rows), "groups": rows}
    except Exception as exc:
        return error_payload("get_host_groups", exc)


@tool(name="zabbix.get_hosts_in_group")  # type: ignore[operator]
def get_hosts_in_group(
    group: Annotated[str, "Group name (full or partial)"],
    limit: Annotated[int, "Maximum hosts to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """List hosts that belong to a given host group."""
    try:
        zabbix_gateway = gateway()
        groups = zabbix_gateway.call_list(
            "hostgroup.get",
            output=["groupid", "name"],
            search={"name": group},
            searchByAny=True,
            sortfield=["name"],
            sortorder="ASC",
            limit=1,
        )
        if not groups:
            return {"error": f"group_not_found:{group}"}
        selected_group = groups[0]
        groupid = str(selected_group.get("groupid", ""))
        hosts = zabbix_gateway.list_hosts_raw(
            groupids=[groupid],
            limit=clamp_limit(limit),
        )
        rows = [host_brief(host) for host in hosts]
        return {
            "group": {
                "groupid": groupid,
                "name": str(selected_group.get("name", "")),
            },
            "count": len(rows),
            "hosts": rows,
        }
    except Exception as exc:
        return error_payload("get_hosts_in_group", exc)


@tool(name="zabbix.get_problems")  # type: ignore[operator]
def get_problems(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP to scope problems to one device.",
    ] = None,
    group: Annotated[str | None, "Optional host-group filter"] = None,
    min_severity: Annotated[
        str | None,
        "Optional minimum severity. Default is average.",
    ] = DEFAULT_MIN_SEVERITY,
    hours: Annotated[int | float | None, "Lookback window in hours."] = DEFAULT_HOURS,
    unacknowledged_only: Annotated[
        bool,
        "If true, include only unacknowledged problems.",
    ] = False,
    unsuppressed_only: Annotated[
        bool,
        "If true, exclude suppressed problems.",
    ] = True,
    limit: Annotated[int, "Maximum problems to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return active problems with rich trigger/host context."""
    try:
        zabbix_gateway = gateway()
        return build_problems_payload(
            zabbix_gateway,
            hostname_or_ip=hostname_or_ip,
            group=group,
            min_severity=min_severity,
            hours=hours,
            unacknowledged_only=unacknowledged_only,
            unsuppressed_only=unsuppressed_only,
            limit=limit,
            active_only=True,
            recent=True,
            host_not_found_tool_name="get_problems",
        )
    except Exception as exc:
        return error_payload("get_problems", exc)


@tool(name="zabbix.get_recent_problems")  # type: ignore[operator]
def get_recent_problems(
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    min_severity: Annotated[
        str | None,
        "Optional minimum severity. Default is average.",
    ] = DEFAULT_MIN_SEVERITY,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return current + recently resolved problems within a lookback period."""
    try:
        zabbix_gateway = gateway()
        return build_problems_payload(
            zabbix_gateway,
            min_severity=min_severity,
            hours=hours,
            unacknowledged_only=False,
            unsuppressed_only=True,
            limit=limit,
            active_only=False,
            recent=True,
            host_not_found_tool_name="get_recent_problems",
        )
    except Exception as exc:
        return error_payload("get_recent_problems", exc)


@tool(name="zabbix.get_host_problems")  # type: ignore[operator]
def get_host_problems(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    min_severity: Annotated[
        str | None,
        "Optional minimum severity. Default is average.",
    ] = DEFAULT_MIN_SEVERITY,
    unacknowledged_only: Annotated[
        bool,
        "If true, include only unacknowledged problems.",
    ] = False,
    unsuppressed_only: Annotated[
        bool,
        "If true, exclude suppressed problems.",
    ] = True,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return current + recent problems for one host."""
    try:
        zabbix_gateway = gateway()
        payload = build_problems_payload(
            zabbix_gateway,
            hostname_or_ip=hostname_or_ip,
            min_severity=min_severity,
            hours=hours,
            unacknowledged_only=unacknowledged_only,
            unsuppressed_only=unsuppressed_only,
            limit=limit,
            active_only=False,
            recent=True,
            host_not_found_tool_name="get_host_problems",
        )
        payload["hostname_or_ip"] = hostname_or_ip
        return payload
    except Exception as exc:
        return error_payload("get_host_problems", exc)


@tool(name="zabbix.get_trigger_problems")  # type: ignore[operator]
def get_trigger_problems(
    trigger: Annotated[
        str,
        "Trigger ID or text match against trigger description.",
    ],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return problems linked to one trigger."""
    try:
        zabbix_gateway = gateway()
        trigger_lc = normalize(trigger)
        trigger_rows: list[dict[str, Any]]
        if trigger_lc.isdigit():
            trigger_rows = zabbix_gateway.call_list(
                "trigger.get",
                output=["triggerid", "description", "priority", "status"],
                triggerids=[trigger_lc],
            )
        else:
            trigger_rows = zabbix_gateway.call_list(
                "trigger.get",
                output=["triggerid", "description", "priority", "status"],
                search={"description": trigger},
                searchByAny=True,
                sortfield=["lastchange"],
                sortorder="DESC",
                limit=25,
            )

        if not trigger_rows:
            return {"error": f"trigger_not_found:{trigger}"}

        selected = trigger_rows[0]
        triggerid = str(selected.get("triggerid", ""))
        params: dict[str, Any] = {
            "output": [
                "eventid",
                "name",
                "severity",
                "clock",
                "acknowledged",
                "r_eventid",
                "suppressed",
                "objectid",
            ],
            "recent": True,
            "time_from": time_from_hours(hours),
            "objectids": [triggerid],
            "sortfield": "eventid",
            "sortorder": "DESC",
            "limit": clamp_limit(limit),
        }
        events = zabbix_gateway.call_list("problem.get", **params)
        events.sort(
            key=lambda event: (
                int(event.get("severity", 0) or 0),
                int(event.get("eventid", 0) or 0),
            ),
            reverse=True,
        )
        trigger_map = enrich_trigger_map(zabbix_gateway, [triggerid])
        rows = [normalize_problem_row(event, trigger_map) for event in events]
        return {
            "trigger": trigger_map.get(triggerid),
            "count": len(rows),
            "problems": rows,
            "hours": hours if hours is not None else DEFAULT_HOURS,
        }
    except Exception as exc:
        return error_payload("get_trigger_problems", exc)


@tool(name="zabbix.get_triggers")  # type: ignore[operator]
def get_triggers(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    min_severity: Annotated[
        str | None,
        "Optional minimum trigger severity. Default is average.",
    ] = DEFAULT_MIN_SEVERITY,
    include_disabled: Annotated[
        bool,
        "If true, include disabled triggers.",
    ] = False,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return trigger definitions and state for a host."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway, hostname_or_ip, tool_name="get_triggers"
            )

        rows = zabbix_gateway.call_list(
            "trigger.get",
            output=[
                "triggerid",
                "description",
                "priority",
                "status",
                "lastchange",
                "expression",
                "recovery_expression",
                "state",
                "error",
                "value",
            ],
            selectTags=["tag", "value"],
            hostids=[str(host.get("hostid", ""))],
            sortfield=["priority", "lastchange"],
            sortorder="DESC",
            limit=clamp_limit(limit),
        )

        threshold = severity_threshold(min_severity)
        triggers: list[dict[str, Any]] = []
        for row in rows:
            severity = SEVERITY_NUM_TO_NAME.get(
                str(row.get("priority", "0")), "not_classified"
            )
            if SEVERITY_ORDER.get(severity, 0) < threshold:
                continue
            enabled = str(row.get("status", "0")) == "0"
            if not include_disabled and not enabled:
                continue
            triggers.append(
                {
                    "triggerid": str(row.get("triggerid", "")),
                    "hostname": str(host.get("host", "")),
                    "description": str(row.get("description", "")),
                    "enabled": enabled,
                    "severity": severity,
                    "last_change": to_iso(row.get("lastchange")),
                    "expression": str(row.get("expression", "")),
                    "recovery_expression": str(row.get("recovery_expression", "")),
                    "state": str(row.get("state", "")),
                    "error": str(row.get("error", "")),
                    "value": str(row.get("value", "")),
                    "tags": [
                        {
                            "tag": str(tag.get("tag", "")),
                            "value": str(tag.get("value", "")),
                        }
                        for tag in (row.get("tags") or [])
                    ],
                }
            )

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "count": len(triggers),
            "filters": {
                "min_severity": normalize(min_severity) or DEFAULT_MIN_SEVERITY,
                "include_disabled": include_disabled,
            },
            "triggers": triggers,
        }
    except Exception as exc:
        return error_payload("get_triggers", exc)


@tool(name="zabbix.get_trigger_details")  # type: ignore[operator]
def get_trigger_details(
    trigger_id: Annotated[str, "Trigger ID"],
) -> dict[str, Any]:
    """Get full trigger details including dependencies and recovery logic."""
    try:
        zabbix_gateway = gateway()
        rows = zabbix_gateway.call_list(
            "trigger.get",
            output="extend",
            triggerids=[trigger_id],
            expandDescription=True,
            expandExpression=True,
            selectDependencies="extend",
            selectTags="extend",
            selectHosts=["hostid", "host", "name"],
            selectItems=["itemid", "name", "key_", "value_type"],
        )
        if not rows:
            return {"error": f"trigger_not_found:{trigger_id}"}
        row = rows[0]
        return {
            "triggerid": str(row.get("triggerid", "")),
            "description": str(row.get("description", "")),
            "expression": str(row.get("expression", "")),
            "recovery_expression": str(row.get("recovery_expression", "")),
            "enabled": str(row.get("status", "0")) == "0",
            "severity": SEVERITY_NUM_TO_NAME.get(
                str(row.get("priority", "0")), "not_classified"
            ),
            "last_change": to_iso(row.get("lastchange")),
            "state": str(row.get("state", "")),
            "error": str(row.get("error", "")),
            "dependencies": [
                {
                    "triggerid": str(dep.get("triggerid", "")),
                    "description": str(dep.get("description", "")),
                }
                for dep in (row.get("dependencies") or [])
            ],
            "hosts": [
                {
                    "hostid": str(host.get("hostid", "")),
                    "hostname": str(host.get("host", "")),
                    "display_name": str(host.get("name", "")),
                }
                for host in (row.get("hosts") or [])
            ],
            "items": [
                {
                    "itemid": str(item.get("itemid", "")),
                    "name": str(item.get("name", "")),
                    "key": str(item.get("key_", "")),
                    "value_type": str(item.get("value_type", "")),
                }
                for item in (row.get("items") or [])
            ],
            "tags": [
                {
                    "tag": str(tag.get("tag", "")),
                    "value": str(tag.get("value", "")),
                }
                for tag in (row.get("tags") or [])
            ],
        }
    except Exception as exc:
        return error_payload("get_trigger_details", exc)


@tool(name="zabbix.get_latest_metrics_data")  # type: ignore[operator]
def get_latest_metrics_data(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    key_patterns: Annotated[
        list[str] | None,
        "Optional item key patterns (supports contains or glob).",
    ] = None,
    limit: Annotated[int, "Maximum metrics to return"] = 200,
) -> dict[str, Any]:
    """Return latest metric values from item.lastvalue for one host."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway,
                hostname_or_ip,
                tool_name="get_latest_metrics_data",
            )

        rows = zabbix_gateway.call_list(
            "item.get",
            output=[
                "itemid",
                "hostid",
                "name",
                "key_",
                "lastvalue",
                "units",
                "lastclock",
                "state",
                "status",
                "error",
                "value_type",
            ],
            hostids=[str(host.get("hostid", ""))],
            sortfield=["name"],
            sortorder="ASC",
            limit=clamp_limit(limit),
        )

        metrics: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.get("key_", ""))
            if not matches_pattern(key, key_patterns):
                continue
            metrics.append(
                {
                    "itemid": str(row.get("itemid", "")),
                    "name": str(row.get("name", "")),
                    "key": key,
                    "value": row.get("lastvalue", ""),
                    "unit": str(row.get("units", "")),
                    "last_clock": to_iso(row.get("lastclock")),
                    "enabled": str(row.get("status", "0")) == "0",
                    "state": str(row.get("state", "0")),
                    "error": str(row.get("error", "")),
                    "value_type": str(row.get("value_type", "")),
                }
            )
        metrics.sort(
            key=lambda metric: (
                str(metric.get("last_clock", "")),
                str(metric.get("name", "")),
            ),
            reverse=True,
        )

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "count": len(metrics),
            "filters": {"key_patterns": key_patterns or []},
            "metrics": metrics[: clamp_limit(limit)],
        }
    except Exception as exc:
        return error_payload("get_latest_metrics_data", exc)


@tool(name="zabbix.get_metrics_history")  # type: ignore[operator]
def get_metrics_history(
    item_id: Annotated[str | None, "Optional item ID"] = None,
    item_key: Annotated[str | None, "Optional item key"] = None,
    hostname_or_ip: Annotated[
        str | None,
        "Required with item_key when item_id is not provided.",
    ] = None,
    hours: Annotated[int | float | None, "Lookback window in hours"] = 6,
    aggregation: Annotated[
        str,
        "Aggregation mode: raw/avg/min/max",
    ] = "raw",
    limit: Annotated[int, "Maximum points to return"] = 500,
) -> dict[str, Any]:
    """Return item history points (raw or trend aggregation)."""
    try:
        if not item_id and not item_key:
            return {"error": "item_id_or_item_key_required"}

        zabbix_gateway = gateway()

        item_rows: list[dict[str, Any]] = []
        if item_id:
            item_rows = zabbix_gateway.call_list(
                "item.get",
                output=["itemid", "name", "key_", "units", "value_type", "hostid"],
                itemids=[str(item_id)],
                limit=1,
            )
        else:
            if not hostname_or_ip:
                return {"error": "hostname_or_ip_required_with_item_key"}
            host = zabbix_gateway.resolve_host(hostname_or_ip)
            if not host:
                return host_not_found(
                    zabbix_gateway,
                    hostname_or_ip,
                    tool_name="get_metrics_history",
                )
            item_rows = zabbix_gateway.call_list(
                "item.get",
                output=["itemid", "name", "key_", "units", "value_type", "hostid"],
                hostids=[str(host.get("hostid", ""))],
                filter={"key_": [str(item_key)]},
                limit=1,
            )

        if not item_rows:
            if item_id:
                return {"error": f"item_not_found:{item_id}"}
            return {"error": f"item_not_found:{item_key}"}

        item = item_rows[0]
        itemid = str(item.get("itemid", ""))
        value_type = str(item.get("value_type", "0"))
        aggregation_lc = normalize(aggregation) or "raw"
        since_ts = time_from_hours(hours)

        points: list[dict[str, Any]] = []
        if aggregation_lc == "raw":
            history_rows = zabbix_gateway.call_list(
                "history.get",
                output=["itemid", "clock", "value", "ns"],
                history=int(value_type),
                itemids=[itemid],
                sortfield=["clock"],
                sortorder="DESC",
                time_from=since_ts,
                limit=clamp_limit(limit),
            )
            points = [
                {
                    "clock": to_iso(row.get("clock")),
                    "value": row.get("value", ""),
                    "ns": str(row.get("ns", "")),
                }
                for row in history_rows
            ]
        elif aggregation_lc in {"avg", "min", "max"}:
            if value_type not in {"0", "3"}:
                return {
                    "error": "aggregation_requires_numeric_item",
                    "value_type": value_type,
                }
            trend_rows = zabbix_gateway.call_list(
                "trend.get",
                output=[
                    "itemid",
                    "clock",
                    "num",
                    "value_min",
                    "value_avg",
                    "value_max",
                ],
                itemids=[itemid],
                time_from=since_ts,
                sortfield=["clock"],
                sortorder="DESC",
                limit=clamp_limit(limit),
            )
            field = {
                "avg": "value_avg",
                "min": "value_min",
                "max": "value_max",
            }[aggregation_lc]
            points = [
                {
                    "clock": to_iso(row.get("clock")),
                    "value": row.get(field, ""),
                    "samples": int(row.get("num", 0) or 0),
                }
                for row in trend_rows
            ]
        else:
            return {"error": f"invalid_aggregation:{aggregation}"}

        return {
            "item": {
                "itemid": itemid,
                "name": str(item.get("name", "")),
                "key": str(item.get("key_", "")),
                "unit": str(item.get("units", "")),
                "value_type": value_type,
            },
            "aggregation": aggregation_lc,
            "hours": hours,
            "count": len(points),
            "points": points,
        }
    except Exception as exc:
        return error_payload("get_metrics_history", exc)


@tool(name="zabbix.get_host_metrics_summary")  # type: ignore[operator]
def get_host_metrics_summary(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    key_patterns: Annotated[
        list[str] | None,
        "Optional metric key patterns for summary focus",
    ] = None,
) -> dict[str, Any]:
    """Return compact host metric summary with utilization and item errors."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway,
                hostname_or_ip,
                tool_name="get_host_metrics_summary",
            )

        rows = zabbix_gateway.call_list(
            "item.get",
            output=[
                "itemid",
                "name",
                "key_",
                "lastvalue",
                "units",
                "lastclock",
                "state",
                "status",
                "error",
            ],
            hostids=[str(host.get("hostid", ""))],
            sortfield=["name"],
            limit=500,
        )

        utilization: list[dict[str, Any]] = []
        error_items: list[dict[str, Any]] = []
        inspected = 0
        for row in rows:
            key = str(row.get("key_", ""))
            if not matches_pattern(key, key_patterns):
                continue
            inspected += 1

            raw_value = row.get("lastvalue", "")
            unit = str(row.get("units", ""))
            if "%" in unit:
                try:
                    numeric = float(raw_value)
                    utilization.append(
                        {
                            "itemid": str(row.get("itemid", "")),
                            "name": str(row.get("name", "")),
                            "key": key,
                            "value": numeric,
                            "unit": unit,
                            "last_clock": to_iso(row.get("lastclock")),
                        }
                    )
                except (TypeError, ValueError):
                    pass

            if str(row.get("state", "0")) != "0" or str(row.get("status", "0")) != "0":
                error_items.append(
                    {
                        "itemid": str(row.get("itemid", "")),
                        "name": str(row.get("name", "")),
                        "key": key,
                        "state": str(row.get("state", "")),
                        "enabled": str(row.get("status", "0")) == "0",
                        "error": str(row.get("error", "")),
                    }
                )

        utilization.sort(key=lambda row: float(row.get("value", 0.0)), reverse=True)

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "inspected_metric_count": inspected,
            "top_utilized_resources": utilization[:5],
            "error_items": error_items,
            "summary": {
                "top_utilized_count": min(len(utilization), 5),
                "error_item_count": len(error_items),
            },
        }
    except Exception as exc:
        return error_payload("get_host_metrics_summary", exc)


@tool(name="zabbix.get_events")  # type: ignore[operator]
def get_events(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP to scope events.",
    ] = None,
    problem_event_id: Annotated[
        str | None,
        "Optional problem event ID to fetch surrounding trigger events.",
    ] = None,
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    include_ok_events: Annotated[
        bool,
        "If true, include OK/recovery events alongside problem events.",
    ] = True,
    limit: Annotated[int, "Maximum events to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return trigger event timeline."""
    try:
        zabbix_gateway = gateway()

        hostids: list[str] = []
        if hostname_or_ip:
            host = zabbix_gateway.resolve_host(hostname_or_ip)
            if not host:
                return host_not_found(
                    zabbix_gateway, hostname_or_ip, tool_name="get_events"
                )
            hostids = [str(host.get("hostid", ""))]

        objectids: list[str] = []
        if problem_event_id:
            event_lookup = zabbix_gateway.call_list(
                "event.get",
                output=["eventid", "objectid", "clock", "name", "severity", "value"],
                eventids=[problem_event_id],
                limit=1,
            )
            if not event_lookup:
                return {"error": f"event_not_found:{problem_event_id}"}
            objectids = [str(event_lookup[0].get("objectid", ""))]

        params: dict[str, Any] = {
            "output": [
                "eventid",
                "name",
                "severity",
                "clock",
                "acknowledged",
                "value",
                "objectid",
                "r_eventid",
            ],
            "selectHosts": ["hostid", "host", "name"],
            "source": 0,
            "object": 0,
            "time_from": time_from_hours(hours),
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "limit": clamp_limit(limit),
        }
        if hostids:
            params["hostids"] = hostids
        if objectids:
            params["objectids"] = objectids

        rows = zabbix_gateway.call_list("event.get", **params)

        events: list[dict[str, Any]] = []
        for row in rows:
            is_problem = str(row.get("value", "1")) == "1"
            if not include_ok_events and not is_problem:
                continue
            hosts = row.get("hosts") or []
            host = hosts[0] if hosts else {}
            events.append(
                {
                    "eventid": str(row.get("eventid", "")),
                    "hostname": str(host.get("host", "")),
                    "host_display_name": str(host.get("name", "")),
                    "name": str(row.get("name", "")),
                    "severity": SEVERITY_NUM_TO_NAME.get(
                        str(row.get("severity", "0")), "not_classified"
                    ),
                    "kind": "problem" if is_problem else "ok",
                    "acknowledged": str(row.get("acknowledged", "0")) == "1",
                    "clock": to_iso(row.get("clock")),
                    "objectid": str(row.get("objectid", "")),
                }
            )

        return {
            "count": len(events),
            "filters": {
                "hostname_or_ip": hostname_or_ip,
                "problem_event_id": problem_event_id,
                "hours": hours if hours is not None else DEFAULT_HOURS,
                "include_ok_events": include_ok_events,
            },
            "events": events[: clamp_limit(limit)],
        }
    except Exception as exc:
        return error_payload("get_events", exc)


@tool(name="zabbix.get_audit_log")  # type: ignore[operator]
def get_audit_log(
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    actor: Annotated[str | None, "Optional actor/username filter"] = None,
    action: Annotated[str | None, "Optional action filter"] = None,
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return recent Zabbix audit entries when auditlog API is available."""
    try:
        zabbix_gateway = gateway()
        rows = zabbix_gateway.call_list(
            "auditlog.get",
            output="extend",
            time_from=time_from_hours(hours),
            sortfield=["clock"],
            sortorder="DESC",
            limit=clamp_limit(limit),
        )

        actor_lc = normalize(actor)
        action_lc = normalize(action)
        entries: list[dict[str, Any]] = []
        for row in rows:
            username = str(row.get("username") or row.get("userid") or "")
            action_text = str(row.get("action", ""))
            if actor_lc and actor_lc not in username.lower():
                continue
            if action_lc and action_lc not in action_text.lower():
                continue
            entries.append(
                {
                    "auditid": str(row.get("auditid", "")),
                    "clock": to_iso(row.get("clock")),
                    "actor": username,
                    "action": action_text,
                    "ip": str(row.get("ip", "")),
                    "resource_type": str(row.get("resourcetype", "")),
                    "resource_name": str(row.get("resourcename", "")),
                    "details": row.get("details", ""),
                }
            )

        return {
            "count": len(entries),
            "filters": {
                "hours": hours if hours is not None else DEFAULT_HOURS,
                "actor": actor,
                "action": action,
            },
            "entries": entries,
        }
    except Exception as exc:
        return error_payload("get_audit_log", exc)


@tool(name="zabbix.get_host_templates")  # type: ignore[operator]
def get_host_templates(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Return templates linked to a host."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway,
                hostname_or_ip,
                tool_name="get_host_templates",
            )
        templates = [
            {
                "templateid": str(entry.get("templateid", "")),
                "hostname": str(entry.get("host", "")),
                "name": str(entry.get("name", "")),
            }
            for entry in (host.get("parentTemplates") or [])
        ]
        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "count": len(templates),
            "templates": templates,
        }
    except Exception as exc:
        return error_payload("get_host_templates", exc)


@tool(name="zabbix.get_maintenance")  # type: ignore[operator]
def get_maintenance(
    hostname_or_ip: Annotated[
        str | None,
        "Optional hostname/IP. If omitted, returns active maintenance windows.",
    ] = None,
) -> dict[str, Any]:
    """Return maintenance state/windows globally or for one host."""
    try:
        zabbix_gateway = gateway()
        hostids: list[str] = []
        resolved_host: dict[str, Any] | None = None
        if hostname_or_ip:
            resolved_host = zabbix_gateway.resolve_host(hostname_or_ip)
            if not resolved_host:
                return host_not_found(
                    zabbix_gateway, hostname_or_ip, tool_name="get_maintenance"
                )
            hostids = [str(resolved_host.get("hostid", ""))]

        rows = zabbix_gateway.call_list(
            "maintenance.get",
            output=[
                "maintenanceid",
                "name",
                "active_since",
                "active_till",
                "description",
                "maintenance_type",
            ],
            selectHosts=["hostid", "host", "name"],
            selectTags="extend",
        )

        entries: list[dict[str, Any]] = []
        for row in rows:
            hosts = row.get("hosts") or []
            if hostids:
                hostid_set = {str(item.get("hostid", "")) for item in hosts}
                if not set(hostids).intersection(hostid_set):
                    continue
            entries.append(
                {
                    "maintenanceid": str(row.get("maintenanceid", "")),
                    "name": str(row.get("name", "")),
                    "active_since": to_iso(row.get("active_since")),
                    "active_till": to_iso(row.get("active_till")),
                    "description": str(row.get("description", "")),
                    "maintenance_type": str(row.get("maintenance_type", "")),
                    "hosts": [
                        {
                            "hostid": str(host.get("hostid", "")),
                            "hostname": str(host.get("host", "")),
                            "display_name": str(host.get("name", "")),
                        }
                        for host in hosts
                    ],
                    "tags": [
                        {
                            "tag": str(tag.get("tag", "")),
                            "value": str(tag.get("value", "")),
                            "operator": str(tag.get("operator", "")),
                        }
                        for tag in (row.get("tags") or [])
                    ],
                }
            )

        return {
            "hostname_or_ip": hostname_or_ip,
            "host_status": (host_status(resolved_host) if resolved_host else None),
            "count": len(entries),
            "maintenance": entries,
        }
    except Exception as exc:
        return error_payload("get_maintenance", exc)


@tool(name="zabbix.get_proxies")  # type: ignore[operator]
def get_proxies(
    limit: Annotated[int, "Maximum rows to return"] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return Zabbix proxy status and inventory."""
    try:
        zabbix_gateway = gateway()
        rows = zabbix_gateway.call_list(
            "proxy.get",
            output="extend",
            selectHosts=["hostid"],
            sortfield=["name"],
            sortorder="ASC",
            limit=clamp_limit(limit),
        )
        proxies = [
            {
                "proxyid": str(row.get("proxyid", "")),
                "name": str(row.get("name") or row.get("host") or ""),
                "status": str(row.get("status", "")),
                "last_seen": to_iso(row.get("lastaccess")),
                "version": str(row.get("version", "")),
                "compatibility": str(row.get("compatibility", "")),
                "host_count": len(row.get("hosts") or []),
            }
            for row in rows
        ]
        return {
            "count": len(proxies),
            "proxies": proxies,
        }
    except Exception as exc:
        return error_payload("get_proxies", exc)


@tool(name="zabbix.get_zabbix_server_status")  # type: ignore[operator]
def get_zabbix_server_status() -> dict[str, Any]:
    """Return high-level Zabbix API/server status indicators."""
    try:
        zabbix_gateway = gateway()

        api_version = zabbix_gateway.api_version()
        total_hosts = zabbix_gateway.call_count(
            "host.get", output=["hostid"], countOutput=True
        )
        enabled_hosts = zabbix_gateway.call_count(
            "host.get", output=["hostid"], countOutput=True, filter={"status": 0}
        )
        active_problems = zabbix_gateway.call_count(
            "problem.get", output=["eventid"], countOutput=True
        )
        proxy_count = zabbix_gateway.call_count(
            "proxy.get", output=["proxyid"], countOutput=True
        )

        return {
            "api_version": api_version,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "inventory": {
                "total_hosts": total_hosts,
                "enabled_hosts": enabled_hosts,
                "proxy_count": proxy_count,
            },
            "alerts": {
                "active_problem_count": active_problems,
            },
            "queue": {
                "status": "not_exposed_via_current_api",
            },
            "performance": {
                "status": "api_reachable",
            },
        }
    except Exception as exc:
        return error_payload("get_zabbix_server_status", exc)


@tool(name="zabbix.diagnose_host")  # type: ignore[operator]
def diagnose_host(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
) -> dict[str, Any]:
    """One-shot host diagnostic summary from multiple Zabbix data slices."""
    try:
        zabbix_gateway = gateway()
        host = zabbix_gateway.resolve_host(hostname_or_ip)
        if not host:
            return host_not_found(
                zabbix_gateway, hostname_or_ip, tool_name="diagnose_host"
            )

        problem_payload = build_problems_payload(
            zabbix_gateway,
            hostname_or_ip=hostname_or_ip,
            min_severity=DEFAULT_MIN_SEVERITY,
            hours=hours,
            unacknowledged_only=False,
            unsuppressed_only=True,
            limit=20,
            active_only=False,
            recent=True,
            host_not_found_tool_name="diagnose_host",
        )

        interfaces: list[dict[str, Any]] = []
        down_interfaces = 0
        for iface in host.get("interfaces") or []:
            oper = "up" if str(iface.get("available", "0")) == "1" else "down"
            if oper != "up" or str(iface.get("error", "")):
                down_interfaces += 1
            interfaces.append(
                {
                    "name": str(
                        iface.get("dns")
                        or iface.get("ip")
                        or iface.get("interfaceid")
                        or ""
                    ),
                    "type": IFACE_TYPE_MAP.get(str(iface.get("type", "")), "unknown"),
                    "ip": str(iface.get("ip", "")),
                    "port": str(iface.get("port", "")),
                    "oper_status": oper,
                    "error": str(iface.get("error", "")),
                }
            )

        metric_rows = zabbix_gateway.call_list(
            "item.get",
            output=[
                "itemid",
                "hostid",
                "name",
                "key_",
                "lastvalue",
                "units",
                "lastclock",
                "state",
                "status",
                "error",
                "value_type",
            ],
            hostids=[str(host.get("hostid", ""))],
            sortfield=["name"],
            sortorder="ASC",
            limit=30,
        )
        latest_metrics = [
            {
                "itemid": str(row.get("itemid", "")),
                "name": str(row.get("name", "")),
                "key": str(row.get("key_", "")),
                "value": row.get("lastvalue", ""),
                "unit": str(row.get("units", "")),
                "last_clock": to_iso(row.get("lastclock")),
                "enabled": str(row.get("status", "0")) == "0",
                "state": str(row.get("state", "0")),
                "error": str(row.get("error", "")),
                "value_type": str(row.get("value_type", "")),
            }
            for row in metric_rows
            if matches_pattern(
                str(row.get("key_", "")), ["*cpu*", "*memory*", "*icmp*", "*if*"]
            )
        ]
        latest_metrics.sort(
            key=lambda metric: (
                str(metric.get("last_clock", "")),
                str(metric.get("name", "")),
            ),
            reverse=True,
        )

        event_rows = zabbix_gateway.call_list(
            "event.get",
            output=[
                "eventid",
                "name",
                "severity",
                "clock",
                "acknowledged",
                "value",
                "objectid",
                "r_eventid",
            ],
            selectHosts=["hostid", "host", "name"],
            source=0,
            object=0,
            hostids=[str(host.get("hostid", ""))],
            time_from=time_from_hours(hours),
            sortfield=["clock"],
            sortorder="DESC",
            limit=20,
        )
        recent_events = []
        for row in event_rows:
            hosts = row.get("hosts") or []
            host_entry = hosts[0] if hosts else {}
            is_problem = str(row.get("value", "1")) == "1"
            recent_events.append(
                {
                    "eventid": str(row.get("eventid", "")),
                    "hostname": str(host_entry.get("host", "")),
                    "host_display_name": str(host_entry.get("name", "")),
                    "name": str(row.get("name", "")),
                    "severity": SEVERITY_NUM_TO_NAME.get(
                        str(row.get("severity", "0")), "not_classified"
                    ),
                    "kind": "problem" if is_problem else "ok",
                    "acknowledged": str(row.get("acknowledged", "0")) == "1",
                    "clock": to_iso(row.get("clock")),
                    "objectid": str(row.get("objectid", "")),
                }
            )

        host_state = host_status(host)
        problem_count = int(problem_payload.get("count", 0) or 0)
        summary = (
            f"Host {host.get('host', '')} is {host_state}; "
            f"{problem_count} recent problems in the last {int(hours or DEFAULT_HOURS)}h; "
            f"{down_interfaces} interface(s) are down or erroring."
        )

        return {
            "hostname": str(host.get("host", "")),
            "ip": primary_ip(host),
            "hours": hours if hours is not None else DEFAULT_HOURS,
            "status": host_state,
            "problems": problem_payload.get("problems", []),
            "interfaces": interfaces,
            "latest_metrics": latest_metrics,
            "recent_events": recent_events,
            "summary": summary,
        }
    except Exception as exc:
        return error_payload("diagnose_host", exc)


@tool(name="zabbix.get_dashboard_snapshot")  # type: ignore[operator]
def get_dashboard_snapshot(
    dashboard: Annotated[
        str | None,
        "Dashboard slice: problems/hosts/overview.",
    ] = "problems",
    hours: Annotated[int | float | None, "Lookback window in hours"] = DEFAULT_HOURS,
    limit: Annotated[int, "Maximum rows to return"] = 20,
) -> dict[str, Any]:
    """Return compact dashboard-like snapshots for fast triage."""
    try:
        dashboard_lc = normalize(dashboard) or "problems"
        zabbix_gateway = gateway()

        if dashboard_lc == "problems":
            payload = build_problems_payload(
                zabbix_gateway,
                min_severity=DEFAULT_MIN_SEVERITY,
                hours=hours,
                unacknowledged_only=False,
                unsuppressed_only=True,
                limit=limit,
                active_only=False,
                recent=True,
                host_not_found_tool_name="get_dashboard_snapshot",
            )
            return {
                "dashboard": "problems",
                "hours": hours if hours is not None else DEFAULT_HOURS,
                "count": payload.get("count", 0),
                "data": payload.get("problems", []),
            }

        if dashboard_lc == "hosts":
            hosts = zabbix_gateway.list_hosts_raw(limit=clamp_limit(limit))
            rows = [host_brief(host) for host in hosts]
            return {
                "dashboard": "hosts",
                "count": len(rows),
                "data": rows,
            }

        if dashboard_lc == "overview":
            hosts = zabbix_gateway.list_hosts_raw(limit=500)
            active = build_problems_payload(
                zabbix_gateway,
                min_severity=DEFAULT_MIN_SEVERITY,
                hours=hours,
                unacknowledged_only=False,
                unsuppressed_only=True,
                limit=500,
                active_only=True,
                recent=True,
                host_not_found_tool_name="get_dashboard_snapshot",
            )
            return {
                "dashboard": "overview",
                "hours": hours if hours is not None else DEFAULT_HOURS,
                "data": {
                    "host_total": len(hosts),
                    "up_hosts": len(
                        [host for host in hosts if host_status(host) == "up"]
                    ),
                    "down_hosts": len(
                        [host for host in hosts if host_status(host) == "down"]
                    ),
                    "maintenance_hosts": len(
                        [host for host in hosts if host_status(host) == "maintenance"]
                    ),
                    "active_problem_total": active.get("count", 0),
                },
            }

        return {
            "error": f"unknown_dashboard:{dashboard}",
            "available_dashboards": ["problems", "hosts", "overview"],
        }
    except Exception as exc:
        return error_payload("get_dashboard_snapshot", exc)
