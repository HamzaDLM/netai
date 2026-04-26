import re
import subprocess
from pathlib import Path
from typing import Annotated, Any

from app.core.config import project_settings
from app.tools import netai_tool


class BitbucketToolError(RuntimeError):
    """Raised for controlled, user-facing Bitbucket tool failures."""

    pass


def normalize(value: str | None) -> str:
    """Lowercase and trim optional text values."""
    return (value or "").strip().lower()


def _error(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    """Build a consistent error payload for agent/tool responses."""
    return {"error": f"{tool_name}_failed:{exc}"}


def _resolved_repo_path(repo_path: str | Path | None = None) -> Path:
    """Resolve a repo path from argument or configured default clone dir."""
    selected = str(repo_path or project_settings.BITBUCKET_CLONE_DIR).strip()
    if not selected:
        raise BitbucketToolError("missing_repo_path_and_bitbucket_clone_dir")
    return Path(selected).resolve()


def _resolved_repo_url(repo_url: str | None = None) -> str:
    """Resolve a repo URL from argument or configured default Bitbucket URL."""
    selected = (repo_url or project_settings.BITBUCKET_URL).strip()
    if not selected:
        raise BitbucketToolError("missing_repo_url_and_bitbucket_url")
    return selected


def _run_git(
    args: list[str],
    *,
    repo_path: str | Path | None = None,
) -> str:
    """Run a git command and return stdout, raising clean tool errors on failures."""
    command = ["git", *args]
    cwd = str(Path(repo_path).resolve()) if repo_path else None
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise BitbucketToolError("git_not_installed") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or "git_command_failed"
        raise BitbucketToolError(f"git_failed:{details}") from exc

    return result.stdout.strip()


def _clone_repo(
    repo_url: str,
    destination: str | Path,
    *,
    branch: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Clone a repository, or return metadata for an existing clone."""
    target = Path(destination).resolve()
    git_dir = target / ".git"

    if git_dir.exists():
        if refresh:
            _run_git(["fetch", "--all", "--tags", "--prune"], repo_path=target)
            current_branch = _run_git(
                ["rev-parse", "--abbrev-ref", "HEAD"], repo_path=target
            )
            if current_branch != "HEAD":
                has_upstream = True
                try:
                    _run_git(
                        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                        repo_path=target,
                    )
                except BitbucketToolError:
                    has_upstream = False

                # Branches without upstream tracking can still be valid for read-only
                # history lookups; in that case keep fetch results and skip pull.
                if has_upstream:
                    _run_git(["pull", "--ff-only"], repo_path=target)
        head = _run_git(["rev-parse", "HEAD"], repo_path=target)
        current_branch = _run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], repo_path=target
        )
        return {
            "repo_path": str(target),
            "already_cloned": True,
            "branch": current_branch,
            "head": head,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    clone_args = ["clone"]
    if branch:
        clone_args += ["--branch", branch]
    clone_args += [repo_url, str(target)]
    _run_git(clone_args)

    head = _run_git(["rev-parse", "HEAD"], repo_path=target)
    current_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path=target)
    return {
        "repo_path": str(target),
        "already_cloned": False,
        "branch": current_branch,
        "head": head,
    }


def clone_repo(
    repo_url: str,
    destination: str | Path,
    *,
    branch: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Helper alias exposed for tests and local programmatic usage."""
    return _clone_repo(repo_url, destination, branch=branch, refresh=refresh)


def clone_bitbucket_repo(
    *,
    branch: str | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    """Programmatic helper that keeps configured clone up to date."""
    resolved_url = _resolved_repo_url()
    resolved_destination = _resolved_repo_path()
    return _clone_repo(
        resolved_url,
        resolved_destination,
        branch=branch,
        refresh=refresh,
    )


def _ensure_bitbucket_repo() -> Path:
    """Ensure configured repo is available and refreshed before any tool read."""
    clone_bitbucket_repo(refresh=True)
    return _resolved_repo_path()


def _tracked_files(repo_path: str | Path) -> list[str]:
    """List tracked files from the repository index."""
    output = _run_git(["ls-files"], repo_path=repo_path)
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _device_name_from_path(file_path: str) -> str:
    """Extract a device name from a config filename stem."""
    return Path(file_path).stem


def _list_device_files(
    repo_path: str | Path,
    *,
    path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Return tracked files as device/file tuples, optionally filtered by path text."""
    files = _tracked_files(repo_path)
    lookup = normalize(path_contains)

    devices: list[dict[str, Any]] = []
    for file_path in files:
        if lookup and lookup not in normalize(file_path):
            continue
        devices.append(
            {
                "device": _device_name_from_path(file_path),
                "file_path": file_path,
            }
        )

    return sorted(devices, key=lambda item: (item["device"], item["file_path"]))


def list_device_files(
    repo_path: str | Path,
    *,
    path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Helper alias exposed for tests and local programmatic usage."""
    return _list_device_files(repo_path, path_contains=path_contains)


def _matching_device_files(repo_path: str | Path, device: str) -> list[str]:
    """Return tracked-file matches for exact filename or filename stem."""
    lookup = normalize(device)
    if not lookup:
        raise BitbucketToolError("device_is_required")

    matches: list[str] = []
    for file_path in _tracked_files(repo_path):
        base = normalize(Path(file_path).name)
        stem = normalize(Path(file_path).stem)
        if lookup in {base, stem}:
            matches.append(file_path)
    return matches


def _resolve_device_file(repo_path: str | Path, device: str) -> str:
    """Resolve one unique tracked file for a device stem or exact filename."""
    matches = _matching_device_files(repo_path, device)

    if not matches:
        raise BitbucketToolError(f"device_not_found:{device}")
    if len(matches) > 1:
        raise BitbucketToolError(f"ambiguous_device:{device}:{','.join(matches)}")
    return matches[0]


def _file_commit_count(repo_path: str | Path, file_path: str) -> int:
    """Count commits that touched a specific tracked file."""
    output = _run_git(
        ["rev-list", "--count", "HEAD", "--", file_path], repo_path=repo_path
    )
    try:
        return int(output)
    except ValueError:
        return 0


def _last_commit_for_file(repo_path: str | Path, file_path: str) -> dict[str, str]:
    """Fetch latest commit metadata for a tracked file."""
    output = _run_git(
        [
            "log",
            "-n",
            "1",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
            "--",
            file_path,
        ],
        repo_path=repo_path,
    )

    parts = output.split("\x1f")
    if len(parts) != 5:
        raise BitbucketToolError("unexpected_git_log_output")

    return {
        "hash": parts[0],
        "author": parts[1],
        "email": parts[2],
        "date": parts[3],
        "message": parts[4],
    }


def _diff_for_file(repo_path: str | Path, file_path: str, commit_hash: str) -> str:
    """Return unified diff for a file in the selected commit versus its parent."""
    parent_exists = True
    try:
        _run_git(["rev-parse", f"{commit_hash}^"], repo_path=repo_path)
    except BitbucketToolError:
        parent_exists = False

    if parent_exists:
        return _run_git(
            ["diff", "--unified=3", f"{commit_hash}^", commit_hash, "--", file_path],
            repo_path=repo_path,
        )

    return _run_git(
        ["show", "--unified=3", "--pretty=format:", commit_hash, "--", file_path],
        repo_path=repo_path,
    )


def _file_content_at_ref(
    repo_path: str | Path, file_path: str, ref: str = "HEAD"
) -> str:
    """Read file content at a specific git ref."""
    return _run_git(["show", f"{ref}:{file_path}"], repo_path=repo_path)


_SENSITIVE_LINE_PATTERNS: list[re.Pattern[str]] = [
    # Fortinet / Cisco / Juniper / Arista / Nokia style secrets
    re.compile(r"(?i)\bset\s+(?:password|passwd|secret|psksecret|private-key)\b"),
    re.compile(r"(?i)\busername\s+\S+\s+(?:password|secret)\b"),
    re.compile(r"(?i)\benable\s+secret\b"),
    re.compile(r"(?i)\b(?:password|passwd|secret)\s+\d+\s+\S+"),
    re.compile(r"(?i)\b\d+\s+\S*(?:pass|secret|token|key)\S*"),
    # SNMP and AAA
    re.compile(r"(?i)\bsnmp-server\s+community\b"),
    re.compile(r"(?i)\bsnmp-server\s+user\b.*\bauth\b"),
    re.compile(r"(?i)\bsnmp-server\s+user\b.*\bpriv\b"),
    re.compile(r"(?i)\b(?:radius-server|tacacs-server)\s+(?:host\s+\S+\s+)?key\b"),
    re.compile(r"(?i)\bkey-string\b"),
    # Hierarchical CLIs and service configs
    re.compile(r"(?i)\bencrypted-password\b"),
    re.compile(r"(?i)\bauthentication-key\b"),
    re.compile(r"(?i)\bplain-text-password\b"),
    re.compile(r"(?i)\bcommunity\s+(?:\"[^\"]*\"|\S+)"),
    re.compile(r"(?i)\bntp-key\s+\d+\b"),
    re.compile(r"(?i)\b(?:tmsh\s+)?(?:modify|create)\s+auth\s+user\b.*\bpassword\b"),
    # Generic key-value style secrets
    re.compile(r"(?i)\b(?:rootpw|bindpw|shared[-_]?secret|auth[-_]?token)\s*[:=]"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]"),
]


def _is_sensitive_config_line(line: str) -> bool:
    """Return True when a config/diff line appears to contain secret material."""
    return any(pattern.search(line) for pattern in _SENSITIVE_LINE_PATTERNS)


def sanitize_config_text(config_text: str) -> str:
    """Remove lines containing sensitive values from configuration text."""
    if not config_text:
        return config_text

    had_trailing_newline = config_text.endswith("\n")
    kept_lines = [
        line for line in config_text.splitlines() if not _is_sensitive_config_line(line)
    ]
    sanitized = "\n".join(kept_lines)
    if had_trailing_newline and sanitized:
        sanitized += "\n"
    return sanitized


def sanitize_unified_diff(diff_text: str) -> str:
    """Remove diff lines that contain sensitive values while preserving diff headers."""
    if not diff_text:
        return diff_text

    had_trailing_newline = diff_text.endswith("\n")
    sanitized_lines: list[str] = []
    for raw_line in diff_text.splitlines():
        if raw_line.startswith(("+++", "---", "@@")):
            sanitized_lines.append(raw_line)
            continue

        if raw_line and raw_line[0] in {"+", "-", " "}:
            if _is_sensitive_config_line(raw_line[1:]):
                continue
            sanitized_lines.append(raw_line)
            continue

        if _is_sensitive_config_line(raw_line):
            continue
        sanitized_lines.append(raw_line)

    sanitized = "\n".join(sanitized_lines)
    if had_trailing_newline and sanitized:
        sanitized += "\n"
    return sanitized


def _get_device_file_info(repo_path: str | Path, device: str) -> dict[str, Any]:
    """Build last-change details for one device file, including a sanitized diff."""
    file_path = _resolve_device_file(repo_path, device)
    last_commit = _last_commit_for_file(repo_path, file_path)
    commit_count = _file_commit_count(repo_path, file_path)
    last_diff = _diff_for_file(repo_path, file_path, last_commit["hash"])

    return {
        "device": _device_name_from_path(file_path),
        "file_path": file_path,
        "commit_count": commit_count,
        "last_commit": last_commit,
        "last_diff": sanitize_unified_diff(last_diff),
    }


def get_device_file_info(repo_path: str | Path, device: str) -> dict[str, Any]:
    """Helper alias exposed for tests and local programmatic usage."""
    return _get_device_file_info(repo_path, device)


def _device_config_exists(repo_path: str | Path, device: str) -> dict[str, Any]:
    """Quick existence lookup for a device config filename/stem."""
    matches = _matching_device_files(repo_path, device)
    if not matches:
        return {"device_query": device, "exists": False}
    if len(matches) > 1:
        return {"device_query": device, "exists": True, "ambiguous": True}

    file_path = matches[0]
    return {
        "device_query": device,
        "exists": True,
        "device": _device_name_from_path(file_path),
        "file_path": file_path,
    }


def _get_recent_device_config_diff(
    repo_path: str | Path, device: str
) -> dict[str, Any]:
    """Return the latest sanitized config diff payload for one device file."""
    file_path = _resolve_device_file(repo_path, device)
    last_commit = _last_commit_for_file(repo_path, file_path)
    last_diff = sanitize_unified_diff(
        _diff_for_file(repo_path, file_path, last_commit["hash"])
    )

    return {
        "device": _device_name_from_path(file_path),
        "file_path": file_path,
        "last_commit": last_commit,
        "config_diff": {
            "format": "unified",
            "old_path": file_path,
            "new_path": file_path,
            "patch": last_diff,
        },
        "last_diff": last_diff,
    }


def _get_recent_commits_with_devices(
    repo_path: str | Path,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return recent commits with changed files and derived affected devices."""
    if limit < 1:
        raise BitbucketToolError("limit_must_be_positive")

    output = _run_git(
        [
            "log",
            "-n",
            str(limit),
            "--date=iso-strict",
            "--name-only",
            "--pretty=format:__COMMIT__%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
        ],
        repo_path=repo_path,
    )

    if not output:
        return []

    commits: list[dict[str, Any]] = []
    for block in output.split("__COMMIT__\n"):
        if not block.strip():
            continue

        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        header = lines[0]
        changed_files = lines[1:]
        parts = header.split("\x1f")
        if len(parts) != 5:
            continue

        affected_devices = sorted(
            {_device_name_from_path(path) for path in changed_files}
        )

        commits.append(
            {
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "message": parts[4],
                "changed_files": changed_files,
                "affected_devices": affected_devices,
            }
        )

    return commits


def _get_recent_commits_for_host(
    repo_path: str | Path,
    hostname: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Return recent commits that touched the configuration file for one host."""
    if limit < 1:
        raise BitbucketToolError("limit_must_be_positive")

    file_path = _resolve_device_file(repo_path, hostname)
    output = _run_git(
        [
            "log",
            "-n",
            str(limit),
            "--date=iso-strict",
            "--name-only",
            "--pretty=format:__COMMIT__%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
            "--",
            file_path,
        ],
        repo_path=repo_path,
    )

    commits: list[dict[str, Any]] = []
    if output:
        for block in output.split("__COMMIT__\n"):
            if not block.strip():
                continue

            lines = [line for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            header = lines[0]
            changed_files = lines[1:]
            parts = header.split("\x1f")
            if len(parts) != 5:
                continue

            commits.append(
                {
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4],
                    "changed_files": changed_files,
                    "affected_devices": [_device_name_from_path(file_path)],
                }
            )

    device = _device_name_from_path(file_path)
    return {
        "hostname_query": hostname,
        "hostname": device,
        "device": device,
        "file_path": file_path,
        "count": len(commits),
        "commits": commits,
    }


def get_recent_commits_with_devices(
    repo_path: str | Path,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Helper alias exposed for tests and local programmatic usage."""
    return _get_recent_commits_with_devices(repo_path, limit=limit)


def get_recent_commits_for_host(
    repo_path: str | Path,
    hostname: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Helper alias exposed for tests and local programmatic usage."""
    return _get_recent_commits_for_host(repo_path, hostname, limit=limit)


def list_bitbucket_devices(
    path_contains: str | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Testing helper only: list tracked files as devices (not exposed to the agent)."""
    resolved_repo = _resolved_repo_path(repo_path)
    devices = _list_device_files(resolved_repo, path_contains=path_contains)
    return {"count": len(devices), "devices": devices}


@netai_tool(name="bitbucket_device_config_exists")  # type: ignore[operator]
def bitbucket_device_config_exists(
    device: Annotated[str, "Device name (file stem) or exact filename"],
) -> dict[str, Any]:
    """Check whether a device configuration file exists in the Bitbucket repo."""
    try:
        resolved_repo = _ensure_bitbucket_repo()
        return _device_config_exists(resolved_repo, device)
    except BitbucketToolError as exc:
        return _error("bitbucket_device_config_exists", exc)


@netai_tool(name="bitbucket_get_device_file_info")  # type: ignore[operator]
def get_bitbucket_device_file_info(
    device: Annotated[str, "Device name (file stem) or exact filename"],
) -> dict[str, Any]:
    """Get latest commit metadata and commit count for one device file."""
    try:
        resolved_repo = _ensure_bitbucket_repo()
        info = _get_device_file_info(resolved_repo, device)
        info.pop("last_diff", None)
        return info
    except BitbucketToolError as exc:
        return _error("bitbucket_get_device_file_info", exc)


@netai_tool(name="bitbucket_get_recent_device_config_diff")  # type: ignore[operator]
def get_recent_device_config_diff(
    device: Annotated[str, "Device name (file stem) or exact filename"],
) -> dict[str, Any]:
    """Get the latest sanitized config diff payload for one device file."""
    try:
        resolved_repo = _ensure_bitbucket_repo()
        return _get_recent_device_config_diff(resolved_repo, device)
    except BitbucketToolError as exc:
        return _error("bitbucket_get_recent_device_config_diff", exc)


@netai_tool(name="bitbucket_get_device_configuration")  # type: ignore[operator]
def get_bitbucket_device_configuration(
    device: Annotated[str, "Device name (file stem) or exact filename"],
    commit_ref: Annotated[str | None, "Optional commit hash; defaults to HEAD"] = None,
) -> dict[str, Any]:
    """Return sanitized configuration text for one device file at a commit ref (or HEAD)."""
    try:
        resolved_repo = _ensure_bitbucket_repo()
        file_path = _resolve_device_file(resolved_repo, device)
        ref = commit_ref or "HEAD"
        raw_config = _file_content_at_ref(resolved_repo, file_path, ref=ref)
        return {
            "device": _device_name_from_path(file_path),
            "file_path": file_path,
            "commit_ref": ref,
            "configuration": sanitize_config_text(raw_config),
        }
    except BitbucketToolError as exc:
        return _error("bitbucket_get_device_configuration", exc)


@netai_tool(name="bitbucket_get_recent_commits_for_host")  # type: ignore[operator]
def get_bitbucket_recent_commits_for_host(
    hostname: Annotated[str, "Hostname, device name (file stem), or exact filename"],
    limit: Annotated[int, "Maximum number of recent commits to return"] = 10,
) -> dict[str, Any]:
    """Return recent commits that affected one host's configuration file."""
    try:
        return _get_recent_commits_for_host(
            _ensure_bitbucket_repo(), hostname, limit=limit
        )
    except BitbucketToolError as exc:
        return _error("bitbucket_get_recent_commits_for_host", exc)
