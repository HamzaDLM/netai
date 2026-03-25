import difflib
from typing import Annotated, Any

from haystack.tools import tool


_FAKE_BITBUCKET_REPOS: dict[str, dict[str, Any]] = {
    "network-configs": {
        "workspace": "netops",
        "repo_slug": "network-configs",
        "default_branch": "main",
        "devices": [
            {
                "hostname": "edge-fw-par-01",
                "ip": "10.10.1.1",
                "site": "Paris-DC1",
                "vendor": "Fortinet",
                "platform": "FortiGate 200F",
                "config_path": "configs/paris/edge-fw-par-01.conf",
                "commits": [
                    {
                        "hash": "c318f7a",
                        "author": "NOC Bot",
                        "email": "noc-bot@example.net",
                        "committed_at": "2026-03-02T08:12:24Z",
                        "message": "Baseline import for edge-fw-par-01",
                        "config": """config system global
    set hostname edge-fw-par-01
    set timezone 28
end
config system interface
    edit "wan1"
        set ip 203.0.113.10 255.255.255.252
        set allowaccess ping https ssh
    next
    edit "lan-core"
        set ip 10.10.1.1 255.255.255.0
        set allowaccess ping
    next
end
config router bgp
    set as 65010
    config neighbor
        edit 203.0.113.9
            set remote-as 64512
        next
    end
end
""",
                    },
                    {
                        "hash": "d40a11e",
                        "author": "Alice Martin",
                        "email": "alice.martin@example.net",
                        "committed_at": "2026-03-18T11:30:42Z",
                        "message": "Harden management plane and tighten SSH",
                        "config": """config system global
    set hostname edge-fw-par-01
    set timezone 28
    set admin-scp enable
end
config system interface
    edit "wan1"
        set ip 203.0.113.10 255.255.255.252
        set allowaccess ping https
    next
    edit "lan-core"
        set ip 10.10.1.1 255.255.255.0
        set allowaccess ping
    next
end
config system admin
    edit "ops-admin"
        set accprofile super_admin
        set trusthost1 10.10.0.0 255.255.0.0
    next
end
config router bgp
    set as 65010
    config neighbor
        edit 203.0.113.9
            set remote-as 64512
        next
    end
end
""",
                    },
                    {
                        "hash": "f6b83a2",
                        "author": "Alice Martin",
                        "email": "alice.martin@example.net",
                        "committed_at": "2026-03-24T16:09:11Z",
                        "message": "Add backup neighbor and enable graceful restart",
                        "config": """config system global
    set hostname edge-fw-par-01
    set timezone 28
    set admin-scp enable
end
config system interface
    edit "wan1"
        set ip 203.0.113.10 255.255.255.252
        set allowaccess ping https
    next
    edit "lan-core"
        set ip 10.10.1.1 255.255.255.0
        set allowaccess ping
    next
end
config system admin
    edit "ops-admin"
        set accprofile super_admin
        set trusthost1 10.10.0.0 255.255.0.0
    next
end
config router bgp
    set as 65010
    set graceful-restart enable
    config neighbor
        edit 203.0.113.9
            set remote-as 64512
        next
        edit 198.51.100.17
            set remote-as 64513
        next
    end
end
""",
                    },
                ],
            },
            {
                "hostname": "core-sw-par-01",
                "ip": "10.10.1.11",
                "site": "Paris-DC1",
                "vendor": "Cisco",
                "platform": "Catalyst 9500-40X",
                "config_path": "configs/paris/core-sw-par-01.conf",
                "commits": [
                    {
                        "hash": "99cd11a",
                        "author": "NOC Bot",
                        "email": "noc-bot@example.net",
                        "committed_at": "2026-02-26T07:20:06Z",
                        "message": "Initial baseline commit",
                        "config": """hostname core-sw-par-01
ip routing
aaa new-model
username noc privilege 15 secret 9 $9$M9eB4K3B4x
interface Port-channel10
 description Uplink to spine-01
 switchport trunk allowed vlan 10,20,30
 switchport mode trunk
 spanning-tree portfast trunk
!
interface TenGigabitEthernet1/0/48
 description Member of Po10
 channel-group 10 mode active
!
router bgp 65010
 bgp log-neighbor-changes
 neighbor 10.255.0.1 remote-as 65000
 address-family ipv4
  network 10.10.0.0 mask 255.255.0.0
 exit-address-family
""",
                    },
                    {
                        "hash": "aa217f9",
                        "author": "Mathieu Leroy",
                        "email": "mathieu.leroy@example.net",
                        "committed_at": "2026-03-11T13:55:39Z",
                        "message": "Restrict management ACL on VTY",
                        "config": """hostname core-sw-par-01
ip routing
aaa new-model
username noc privilege 15 secret 9 $9$M9eB4K3B4x
ip access-list standard MGMT_VTY
 permit 10.10.0.0 0.0.255.255
 deny any
line vty 0 4
 access-class MGMT_VTY in
 transport input ssh
!
interface Port-channel10
 description Uplink to spine-01
 switchport trunk allowed vlan 10,20,30
 switchport mode trunk
 spanning-tree portfast trunk
!
interface TenGigabitEthernet1/0/48
 description Member of Po10
 channel-group 10 mode active
!
router bgp 65010
 bgp log-neighbor-changes
 neighbor 10.255.0.1 remote-as 65000
 address-family ipv4
  network 10.10.0.0 mask 255.255.0.0
 exit-address-family
""",
                    },
                     {
                        "hash": "aa2fe7f",
                        "author": "Mathieu Leroy",
                        "email": "mathieu.leroy@example.net",
                        "committed_at": "2026-03-12T13:55:39Z",
                        "message": "Deleting some config lines",
                        "config": """hostname core-sw-par-01
ip routing
aaa new-model
username noc privilege 15 secret 9 $9$M9eB4K3B4x
ip access-list standard MGMT_VTY
 permit 10.10.0.0 0.0.255.255
 deny any
line vty 0 4
 access-class MGMT_VTY in
 transport input ssh
!
line vty 0 4
 access-class MGMT_VTY in
 transport input ssh
!
interface Port-channel10
 description Uplink to spine-01
 switchport trunk allowed vlan 10,20,30
 switchport mode trunk
 spanning-tree portfast trunk
!
""",
                    },
                ],
            },
            {
                "hostname": "dist-rtr-nyc-01",
                "ip": "10.20.1.1",
                "site": "NYC-DC1",
                "vendor": "Juniper",
                "platform": "MX204",
                "config_path": "configs/nyc/dist-rtr-nyc-01.conf",
                "commits": [
                    {
                        "hash": "0cb98ff",
                        "author": "NOC Bot",
                        "email": "noc-bot@example.net",
                        "committed_at": "2026-03-01T06:01:09Z",
                        "message": "Import running config snapshot",
                        "config": """system {
    host-name dist-rtr-nyc-01;
    services {
        ssh {
            protocol-version v2;
        }
    }
}
interfaces {
    xe-0/0/0 {
        unit 0 {
            family inet {
                address 10.20.1.1/24;
            }
        }
    }
}
protocols {
    bgp {
        group TRANSIT-A {
            type external;
            peer-as 64512;
            neighbor 192.0.2.1;
        }
    }
}
""",
                    },
                    {
                        "hash": "3529abd",
                        "author": "Carla Diaz",
                        "email": "carla.diaz@example.net",
                        "committed_at": "2026-03-21T09:44:51Z",
                        "message": "Tune BGP hold timers for transit peers",
                        "config": """system {
    host-name dist-rtr-nyc-01;
    services {
        ssh {
            protocol-version v2;
        }
    }
}
interfaces {
    xe-0/0/0 {
        unit 0 {
            family inet {
                address 10.20.1.1/24;
            }
        }
    }
}
protocols {
    bgp {
        group TRANSIT-A {
            type external;
            hold-time 30;
            peer-as 64512;
            neighbor 192.0.2.1;
        }
    }
}
""",
                    },
                ],
            },
        ],
    }
}


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _iter_devices() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for repo in _FAKE_BITBUCKET_REPOS.values():
        for device in repo["devices"]:
            records.append((repo, device))
    return records


def _resolve_device(hostname_or_ip: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    lookup = _normalize(hostname_or_ip)
    if not lookup:
        return None

    # Prefer exact matching first.
    for repo, device in _iter_devices():
        if lookup in {_normalize(device["hostname"]), _normalize(device["ip"])}:
            return repo, device

    # Then allow prefix/contains matching.
    for repo, device in _iter_devices():
        haystack = f'{device["hostname"]} {device["ip"]} {device["site"]} {device["vendor"]}'.lower()
        if lookup in haystack:
            return repo, device
    return None


def _find_commit(device: dict[str, Any], commit_ref: str) -> dict[str, Any] | None:
    ref = _normalize(commit_ref)
    if not ref:
        return None
    for commit in device["commits"]:
        if _normalize(commit["hash"]) == ref or _normalize(commit["hash"]).startswith(ref):
            return commit
    return None


def _list_commits_newest_first(device: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        device["commits"],
        key=lambda commit: commit["committed_at"],
        reverse=True,
    )


def _summarize_commit(commit: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash": commit["hash"],
        "author": commit["author"],
        "email": commit["email"],
        "committed_at": commit["committed_at"],
        "message": commit["message"],
    }


def _build_unified_diff(
    old_text: str,
    new_text: str,
    *,
    old_label: str,
    new_label: str,
    context_lines: int,
) -> tuple[str, int, int]:
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=old_label,
            tofile=new_label,
            n=context_lines,
            lineterm="",
        )
    )
    added = sum(
        1
        for line in diff_lines
        if line.startswith("+") and not line.startswith(("+++", "++++"))
    )
    removed = sum(
        1
        for line in diff_lines
        if line.startswith("-") and not line.startswith(("---", "----"))
    )
    return "\n".join(diff_lines), added, removed


def _parse_unified_diff(unified_diff: str) -> list[dict[str, Any]]:
    if not unified_diff.strip():
        return []

    files: list[dict[str, Any]] = []
    current_file: dict[str, Any] | None = None
    current_hunk: dict[str, Any] | None = None
    old_lineno = 0
    new_lineno = 0

    for raw_line in unified_diff.splitlines():
        if raw_line.startswith("--- "):
            old_path = raw_line[4:].strip()
            current_file = {
                "old_path": old_path[2:] if old_path.startswith("a/") else old_path,
                "new_path": "",
                "hunks": [],
            }
            files.append(current_file)
            current_hunk = None
            continue

        if raw_line.startswith("+++ "):
            new_path = raw_line[4:].strip()
            if current_file is None:
                current_file = {"old_path": "", "new_path": "", "hunks": []}
                files.append(current_file)
            current_file["new_path"] = new_path[2:] if new_path.startswith("b/") else new_path
            continue

        if raw_line.startswith("@@ "):
            if current_file is None:
                continue
            # Format: @@ -old_start,old_len +new_start,new_len @@ optional header
            marker = raw_line.split("@@")[1].strip()
            parts = marker.split(" ")
            if len(parts) < 2:
                continue
            old_part = parts[0]  # -1,4
            new_part = parts[1]  # +1,6

            old_meta = old_part[1:].split(",")
            new_meta = new_part[1:].split(",")
            old_start = int(old_meta[0]) if old_meta[0].isdigit() else 0
            new_start = int(new_meta[0]) if new_meta[0].isdigit() else 0
            old_count = (
                int(old_meta[1])
                if len(old_meta) > 1 and old_meta[1].isdigit()
                else 1
            )
            new_count = (
                int(new_meta[1])
                if len(new_meta) > 1 and new_meta[1].isdigit()
                else 1
            )

            old_lineno = old_start
            new_lineno = new_start
            current_hunk = {
                "header": raw_line,
                "old_start": old_start,
                "old_lines": old_count,
                "new_start": new_start,
                "new_lines": new_count,
                "lines": [],
            }
            current_file["hunks"].append(current_hunk)
            continue

        if current_hunk is None:
            continue

        if raw_line.startswith("+"):
            current_hunk["lines"].append(
                {
                    "type": "added",
                    "old_lineno": None,
                    "new_lineno": new_lineno,
                    "content": raw_line[1:],
                }
            )
            new_lineno += 1
        elif raw_line.startswith("-"):
            current_hunk["lines"].append(
                {
                    "type": "removed",
                    "old_lineno": old_lineno,
                    "new_lineno": None,
                    "content": raw_line[1:],
                }
            )
            old_lineno += 1
        elif raw_line.startswith(" "):
            current_hunk["lines"].append(
                {
                    "type": "context",
                    "old_lineno": old_lineno,
                    "new_lineno": new_lineno,
                    "content": raw_line[1:],
                }
            )
            old_lineno += 1
            new_lineno += 1
        else:
            current_hunk["lines"].append(
                {
                    "type": "meta",
                    "old_lineno": None,
                    "new_lineno": None,
                    "content": raw_line,
                }
            )

    return files


KNOWN_FAKE_DEVICES: list[dict[str, Any]] = [
    {"hostname": device["hostname"], "ip": device["ip"], "site": device["site"]}
    for _, device in _iter_devices()
]


@tool(name="bitbucket.list_devices")
def list_bitbucket_devices(
    site: Annotated[str | None, "Optional site filter, e.g. Paris-DC1"] = None,
    vendor: Annotated[str | None, "Optional vendor filter, e.g. Cisco"] = None,
) -> dict[str, Any]:
    """List devices that have configuration snapshots in the fake Bitbucket repo."""
    site_lc = _normalize(site)
    vendor_lc = _normalize(vendor)
    devices: list[dict[str, Any]] = []

    for repo, device in _iter_devices():
        if site_lc and _normalize(device["site"]) != site_lc:
            continue
        if vendor_lc and _normalize(device["vendor"]) != vendor_lc:
            continue
        commits = _list_commits_newest_first(device)
        latest = commits[0] if commits else None
        devices.append(
            {
                "hostname": device["hostname"],
                "ip": device["ip"],
                "site": device["site"],
                "vendor": device["vendor"],
                "platform": device["platform"],
                "repo_slug": repo["repo_slug"],
                "config_path": device["config_path"],
                "last_changed_at": latest["committed_at"] if latest else None,
            }
        )

    return {"count": len(devices), "devices": devices}


@tool(name="bitbucket.get_known_devices")
def get_known_fake_devices() -> list[dict[str, Any]]:
    """Return the shared fake device catalog used by all Bitbucket tools."""
    return KNOWN_FAKE_DEVICES


@tool(name="bitbucket.get_device_info")
def get_device_info(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Return metadata about a tracked device configuration and its latest commit."""
    resolved = _resolve_device(hostname_or_ip)
    if not resolved:
        return {"error": f"device_not_found:{hostname_or_ip}", "known_devices": KNOWN_FAKE_DEVICES}
    repo, device = resolved
    commits = _list_commits_newest_first(device)
    latest = commits[0]

    return {
        "hostname": device["hostname"],
        "ip": device["ip"],
        "site": device["site"],
        "vendor": device["vendor"],
        "platform": device["platform"],
        "workspace": repo["workspace"],
        "repo_slug": repo["repo_slug"],
        "branch": repo["default_branch"],
        "config_path": device["config_path"],
        "commit_count": len(commits),
        "last_changed_at": latest["committed_at"],
        "last_commit": _summarize_commit(latest),
    }


@tool(name="bitbucket.get_device_configuration")
def get_device_configuration(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    commit: Annotated[
        str | None,
        "Optional commit hash/prefix. If omitted, returns latest configuration.",
    ] = None,
) -> dict[str, Any]:
    """Get a device configuration snapshot at a specific commit (or latest)."""
    resolved = _resolve_device(hostname_or_ip)
    if not resolved:
        return {"error": f"device_not_found:{hostname_or_ip}", "known_devices": KNOWN_FAKE_DEVICES}
    repo, device = resolved

    selected_commit: dict[str, Any]
    if commit:
        selected_commit = _find_commit(device, commit) or {}
        if not selected_commit:
            return {
                "error": f"commit_not_found:{commit}",
                "hostname": device["hostname"],
                "available_commits": [c["hash"] for c in _list_commits_newest_first(device)],
            }
    else:
        selected_commit = _list_commits_newest_first(device)[0]

    return {
        "hostname": device["hostname"],
        "ip": device["ip"],
        "repo_slug": repo["repo_slug"],
        "branch": repo["default_branch"],
        "config_path": device["config_path"],
        "line_count": len(selected_commit["config"].splitlines()),
        "commit": _summarize_commit(selected_commit),
        "configuration": selected_commit["config"],
    }


@tool(name="bitbucket.get_device_commit_history")
def get_device_commit_history(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    limit: Annotated[int, "Maximum number of commits to return"] = 20,
) -> dict[str, Any]:
    """Return commit history for a device configuration, newest first."""
    if limit < 1:
        return {"error": "limit_must_be_positive"}

    resolved = _resolve_device(hostname_or_ip)
    if not resolved:
        return {"error": f"device_not_found:{hostname_or_ip}", "known_devices": KNOWN_FAKE_DEVICES}
    _, device = resolved
    commits = _list_commits_newest_first(device)
    items = [_summarize_commit(commit) for commit in commits[:limit]]
    return {
        "hostname": device["hostname"],
        "ip": device["ip"],
        "count": len(items),
        "commits": items,
    }


@tool(name="bitbucket.get_device_last_change")
def get_device_last_change(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
) -> dict[str, Any]:
    """Return last change metadata for a device configuration."""
    resolved = _resolve_device(hostname_or_ip)
    if not resolved:
        return {"error": f"device_not_found:{hostname_or_ip}", "known_devices": KNOWN_FAKE_DEVICES}
    _, device = resolved
    latest = _list_commits_newest_first(device)[0]

    return {
        "hostname": device["hostname"],
        "ip": device["ip"],
        "last_changed_at": latest["committed_at"],
        "last_commit": _summarize_commit(latest),
    }


@tool(name="bitbucket.get_device_config_diff")
def get_device_config_diff(
    hostname_or_ip: Annotated[str, "Target device hostname or IP"],
    from_commit: Annotated[
        str | None,
        "Older commit hash/prefix. Defaults to previous commit.",
    ] = None,
    to_commit: Annotated[
        str | None,
        "Newer commit hash/prefix. Defaults to latest commit.",
    ] = None,
    context_lines: Annotated[int, "Unified diff context lines"] = 3,
) -> dict[str, Any]:
    """Generate a commit-style unified diff between two configuration snapshots."""
    if context_lines < 0:
        return {"error": "context_lines_must_be_greater_or_equal_to_zero"}

    resolved = _resolve_device(hostname_or_ip)
    if not resolved:
        return {"error": f"device_not_found:{hostname_or_ip}", "known_devices": KNOWN_FAKE_DEVICES}
    repo, device = resolved

    commits_newest = _list_commits_newest_first(device)
    if len(commits_newest) < 2:
        return {"error": "not_enough_commits_for_diff", "hostname": device["hostname"]}

    selected_to = commits_newest[0] if not to_commit else _find_commit(device, to_commit)
    if not selected_to:
        return {
            "error": f"commit_not_found:{to_commit}",
            "hostname": device["hostname"],
            "available_commits": [c["hash"] for c in commits_newest],
        }

    if from_commit:
        selected_from = _find_commit(device, from_commit)
        if not selected_from:
            return {
                "error": f"commit_not_found:{from_commit}",
                "hostname": device["hostname"],
                "available_commits": [c["hash"] for c in commits_newest],
            }
    else:
        # Default "from" commit is the direct parent in recency order.
        to_index = commits_newest.index(selected_to)
        if to_index + 1 >= len(commits_newest):
            return {
                "error": "parent_commit_not_found",
                "hostname": device["hostname"],
                "hint": "Provide from_commit explicitly.",
            }
        selected_from = commits_newest[to_index + 1]

    diff_text, added_lines, removed_lines = _build_unified_diff(
        selected_from["config"],
        selected_to["config"],
        old_label=f'a/{device["config_path"]}',
        new_label=f'b/{device["config_path"]}',
        context_lines=context_lines,
    )
    files = _parse_unified_diff(diff_text)

    return {
        "hostname": device["hostname"],
        "ip": device["ip"],
        "repo_slug": repo["repo_slug"],
        "config_path": device["config_path"],
        "from_commit": _summarize_commit(selected_from),
        "to_commit": _summarize_commit(selected_to),
        "has_changes": bool(diff_text.strip()),
        "changed_lines": {
            "added": added_lines,
            "removed": removed_lines,
        },
        "unified_diff": diff_text,
        "diff_files": files,
    }
