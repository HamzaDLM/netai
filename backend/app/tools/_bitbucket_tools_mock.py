from typing import Annotated, Any

from haystack.tools import tool

_FAKE_DEVICES: list[dict[str, Any]] = [
    {"device": "edge-fw-par-01", "file_path": "configs/edge-fw-par-01.conf"},
    {"device": "core-sw-par-01", "file_path": "configs/core-sw-par-01.conf"},
    {"device": "dist-rtr-nyc-01", "file_path": "configs/dist-rtr-nyc-01.conf"},
]

_FAKE_CONFIGS: dict[str, str] = {
    "edge-fw-par-01": "hostname edge-fw-par-01\nset firewall policy allow-internal\n",
    "core-sw-par-01": "hostname core-sw-par-01\nrouter bgp 65010\n",
    "dist-rtr-nyc-01": "hostname dist-rtr-nyc-01\nset protocols bgp group isp-a\n",
}

_FAKE_COMMITS: list[dict[str, Any]] = [
    {
        "hash": "mockc0ffee01",
        "author": "NetAI Mock",
        "email": "mock@netai.local",
        "date": "2026-04-01T10:00:00Z",
        "message": "Tune BGP timers on dist-rtr-nyc-01",
        "changed_files": ["configs/dist-rtr-nyc-01.conf"],
        "affected_devices": ["dist-rtr-nyc-01"],
    },
    {
        "hash": "mockc0ffee02",
        "author": "NetAI Mock",
        "email": "mock@netai.local",
        "date": "2026-03-31T16:30:00Z",
        "message": "Harden edge firewall policy",
        "changed_files": ["configs/edge-fw-par-01.conf"],
        "affected_devices": ["edge-fw-par-01"],
    },
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


@tool(name="bitbucket.clone_repo")  # type: ignore[operator]
def clone_bitbucket_repo(
    branch: Annotated[str | None, "Optional branch to clone"] = None,
    refresh: Annotated[bool, "If repo exists locally, fetch updates"] = False,
) -> dict[str, Any]:
    """Mock clone response for local/offline development."""
    return {
        "repo_path": "/mock/repos/network-configs",
        "already_cloned": True,
        "branch": branch or "main",
        "head": _FAKE_COMMITS[0]["hash"],
        "refresh": refresh,
    }


@tool(name="bitbucket.list_devices")  # type: ignore[operator]
def list_bitbucket_devices(
    path_contains: Annotated[str | None, "Optional path substring filter"] = None,
) -> dict[str, Any]:
    """List fake tracked device configuration files."""
    if path_contains:
        needle = _normalize(path_contains)
        devices = [
            row
            for row in _FAKE_DEVICES
            if needle in _normalize(row["file_path"])
            or needle in _normalize(row["device"])
        ]
    else:
        devices = list(_FAKE_DEVICES)
    return {"count": len(devices), "devices": devices}


@tool(name="bitbucket.get_device_file_info")  # type: ignore[operator]
def get_bitbucket_device_file_info(
    device: Annotated[str, "Device name (file stem) or exact filename"],
) -> dict[str, Any]:
    """Return fake latest commit/diff metadata for one device file."""
    device_lc = _normalize(device)
    match = next(
        (row for row in _FAKE_DEVICES if _normalize(row["device"]) == device_lc), None
    )
    if not match:
        return {
            "error": f"bitbucket_get_device_file_info_failed:device_not_found:{device}"
        }

    latest_commit = next(
        (
            commit
            for commit in _FAKE_COMMITS
            if match["device"] in commit["affected_devices"]
        ),
        _FAKE_COMMITS[0],
    )
    return {
        "device": match["device"],
        "file_path": match["file_path"],
        "last_commit": {
            "hash": latest_commit["hash"],
            "author": latest_commit["author"],
            "email": latest_commit["email"],
            "date": latest_commit["date"],
            "message": latest_commit["message"],
        },
        "last_diff": f"--- a/{match['file_path']}\\n+++ b/{match['file_path']}\\n@@ -1,2 +1,3 @@\\n hostname {match['device']}\\n+! mock change",
        "commit_count": 3,
    }


@tool(name="bitbucket.get_device_configuration")  # type: ignore[operator]
def get_bitbucket_device_configuration(
    device: Annotated[str, "Device name (file stem) or exact filename"],
    commit_ref: Annotated[str | None, "Optional commit hash; defaults to HEAD"] = None,
) -> dict[str, Any]:
    """Return fake sanitized configuration text for one device."""
    device_lc = _normalize(device)
    match = next(
        (row for row in _FAKE_DEVICES if _normalize(row["device"]) == device_lc), None
    )
    if not match:
        return {
            "error": f"bitbucket_get_device_configuration_failed:device_not_found:{device}"
        }

    return {
        "device": match["device"],
        "file_path": match["file_path"],
        "commit_ref": commit_ref or "HEAD",
        "configuration": _FAKE_CONFIGS.get(match["device"], ""),
    }


@tool(name="bitbucket.get_recent_commits")  # type: ignore[operator]
def get_bitbucket_recent_commits(
    limit: Annotated[int, "Maximum number of recent commits to return"] = 10,
) -> dict[str, Any]:
    """Return fake latest commits and affected devices."""
    safe_limit = max(1, min(int(limit), 50))
    commits = _FAKE_COMMITS[:safe_limit]
    devices = sorted({d for commit in commits for d in commit["affected_devices"]})
    return {
        "count": len(commits),
        "affected_device_count": len(devices),
        "affected_devices": devices,
        "commits": commits,
    }
