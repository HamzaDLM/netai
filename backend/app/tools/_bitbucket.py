from pathlib import Path
import re
import subprocess
from typing import Annotated, Any

from haystack.tools import tool


class BitbucketToolError(RuntimeError):
    pass


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _error(tool_name: str, exc: Exception | str) -> dict[str, Any]:
    return {"error": f"{tool_name}_failed:{exc}"}


def _run_git(
    args: list[str],
    *,
    repo_path: str | Path | None = None,
) -> str:
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
    target = Path(destination).resolve()
    git_dir = target / ".git"

    if git_dir.exists():
        if refresh:
            _run_git(["fetch", "--all", "--tags"], repo_path=target)
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


def _tracked_files(repo_path: str | Path) -> list[str]:
    output = _run_git(["ls-files"], repo_path=repo_path)
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _device_name_from_path(file_path: str) -> str:
    return Path(file_path).stem


def _list_device_files(
    repo_path: str | Path,
    *,
    path_contains: str | None = None,
) -> list[dict[str, Any]]:
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


def _resolve_device_file(repo_path: str | Path, device: str) -> str:
    lookup = normalize(device)
    if not lookup:
        raise BitbucketToolError("device_is_required")

    matches: list[str] = []
    for file_path in _tracked_files(repo_path):
        base = normalize(Path(file_path).name)
        stem = normalize(Path(file_path).stem)
        if lookup in {base, stem}:
            matches.append(file_path)

    if not matches:
        raise BitbucketToolError(f"device_not_found:{device}")
    if len(matches) > 1:
        raise BitbucketToolError(f"ambiguous_device:{device}:{','.join(matches)}")
    return matches[0]


def _file_commit_count(repo_path: str | Path, file_path: str) -> int:
    output = _run_git(
        ["rev-list", "--count", "HEAD", "--", file_path], repo_path=repo_path
    )
    try:
        return int(output)
    except ValueError:
        return 0


def _last_commit_for_file(repo_path: str | Path, file_path: str) -> dict[str, str]:
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


def _file_content_at_ref(repo_path: str | Path, file_path: str, ref: str = "HEAD") -> str:
    return _run_git(["show", f"{ref}:{file_path}"], repo_path=repo_path)


_SANITIZE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Fortinet-style
    (re.compile(r'(?i)(\bset\s+(?:password|passwd|secret|psksecret|private-key)\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    # Cisco IOS/NX-OS and Arista EOS style
    (re.compile(r'(?i)(\busername\s+\S+\s+(?:password|secret)\s+\d*\s*)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\benable\s+secret\s+\d*\s*)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\bsnmp-server\s+community\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\bsnmp-server\s+user\s+\S+\s+\S+\s+auth\s+\S+\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\bsnmp-server\s+user\s+\S+.*\bpriv\s+\S+\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\b(?:radius-server|tacacs-server)\s+key\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\b(?:radius-server|tacacs-server)\s+host\s+\S+\s+key\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\bkey-string\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    # Juniper, ADVA, Metamako and other hierarchical network CLIs
    # Juniper-style
    (re.compile(r'(?i)(\bencrypted-password\s+)"[^"]*"'), r'\1"<redacted>"'),
    (re.compile(r'(?i)(\bauthentication-key\s+)"[^"]*"'), r'\1"<redacted>"'),
    (re.compile(r'(?i)(\bplain-text-password\s+)"[^"]*"'), r'\1"<redacted>"'),
    (re.compile(r'(?i)(\bcommunity\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\bntp-key\s+\d+\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    # F5 BIG-IP tmsh/uCS snippets
    (re.compile(r'(?i)(\b(?:tmsh\s+)?modify\s+auth\s+user\s+\S+\s+password\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    (re.compile(r'(?i)(\b(?:tmsh\s+)?create\s+auth\s+user\s+\S+\s+password\s+)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    # VMware/Opengear/Oracle/Riverbed text configs typically expose key-value secrets
    (re.compile(r'(?i)((?:rootpw|bindpw|shared[-_]?secret|auth[-_]?token)\s*[:=]\s*)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
    # Generic key-value
    (re.compile(r'(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*)(?:"[^"]*"|\S+)'), r"\1<redacted>"),
]


def sanitize_config_text(config_text: str) -> str:
    sanitized = config_text
    for pattern, replacement in _SANITIZE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_unified_diff(diff_text: str) -> str:
    if not diff_text:
        return diff_text

    sanitized_lines: list[str] = []
    for raw_line in diff_text.splitlines():
        if raw_line.startswith(("+++", "---", "@@")):
            sanitized_lines.append(raw_line)
            continue

        if raw_line and raw_line[0] in {"+", "-", " "}:
            prefix = raw_line[0]
            body = raw_line[1:]
            sanitized_lines.append(prefix + sanitize_config_text(body))
            continue

        sanitized_lines.append(sanitize_config_text(raw_line))

    return "\n".join(sanitized_lines)


def _get_device_file_info(repo_path: str | Path, device: str) -> dict[str, Any]:
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


def _get_recent_commits_with_devices(
    repo_path: str | Path,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
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


@tool(name="bitbucket.clone_repo")
def clone_bitbucket_repo(
    repo_url: Annotated[str, "Git URL/path to clone from"],
    destination: Annotated[str, "Local directory where repo should be cloned"],
    branch: Annotated[str | None, "Optional branch to clone"] = None,
    refresh: Annotated[bool, "If repo exists locally, fetch updates"] = False,
) -> dict[str, Any]:
    """Clone a Bitbucket git repository locally (or return existing clone metadata)."""
    try:
        return _clone_repo(repo_url, destination, branch=branch, refresh=refresh)
    except BitbucketToolError as exc:
        return _error("bitbucket_clone_repo", exc)


@tool(name="bitbucket.list_devices")
def list_bitbucket_devices(
    repo_path: Annotated[str, "Path to a local git clone"],
    path_contains: Annotated[str | None, "Optional path substring filter"] = None,
) -> dict[str, Any]:
    """List tracked files in the repo as devices (device name = file stem)."""
    try:
        devices = _list_device_files(repo_path, path_contains=path_contains)
        return {"count": len(devices), "devices": devices}
    except BitbucketToolError as exc:
        return _error("bitbucket_list_devices", exc)


@tool(name="bitbucket.get_device_file_info")
def get_bitbucket_device_file_info(
    repo_path: Annotated[str, "Path to a local git clone"],
    device: Annotated[str, "Device name (file stem) or exact filename"],
) -> dict[str, Any]:
    """Get last-change details for one device file: message/date/diff and commit count."""
    try:
        return _get_device_file_info(repo_path, device)
    except BitbucketToolError as exc:
        return _error("bitbucket_get_device_file_info", exc)


@tool(name="bitbucket.get_device_configuration")
def get_bitbucket_device_configuration(
    repo_path: Annotated[str, "Path to a local git clone"],
    device: Annotated[str, "Device name (file stem) or exact filename"],
    commit_ref: Annotated[str | None, "Optional commit hash; defaults to HEAD"] = None,
) -> dict[str, Any]:
    """Return sanitized configuration text for one device file at a commit ref (or HEAD)."""
    try:
        file_path = _resolve_device_file(repo_path, device)
        ref = commit_ref or "HEAD"
        raw_config = _file_content_at_ref(repo_path, file_path, ref=ref)
        return {
            "device": _device_name_from_path(file_path),
            "file_path": file_path,
            "commit_ref": ref,
            "configuration": sanitize_config_text(raw_config),
        }
    except BitbucketToolError as exc:
        return _error("bitbucket_get_device_configuration", exc)


@tool(name="bitbucket.get_recent_commits")
def get_bitbucket_recent_commits(
    repo_path: Annotated[str, "Path to a local git clone"],
    limit: Annotated[int, "Maximum number of recent commits to return"] = 10,
) -> dict[str, Any]:
    """Return latest commits and which device files each commit changed."""
    try:
        commits = _get_recent_commits_with_devices(repo_path, limit=limit)
    except BitbucketToolError as exc:
        return _error("bitbucket_get_recent_commits", exc)

    all_devices = sorted(
        {device for commit in commits for device in commit["affected_devices"]}
    )
    return {
        "count": len(commits),
        "affected_device_count": len(all_devices),
        "affected_devices": all_devices,
        "commits": commits,
    }


# Compatibility exports for direct unit tests.
clone_repo = _clone_repo
list_device_files = _list_device_files
get_device_file_info = _get_device_file_info
get_recent_commits_with_devices = _get_recent_commits_with_devices
