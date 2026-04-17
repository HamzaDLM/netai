import subprocess
from pathlib import Path

from app.tools.bitbucket_tools import (
    clone_repo,
    get_device_file_info,
    get_recent_commits_with_devices,
    list_device_files,
    sanitize_config_text,
)


def _git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        check=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo_path: Path, message: str) -> None:
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", message)


def _build_source_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "source-repo"
    repo_path.mkdir()
    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "NetAI Tester")
    _git(repo_path, "config", "user.email", "netai@example.net")

    _write(repo_path / "configs" / "edge-fw-par-01.conf", "hostname edge-fw-par-01\n")
    _write(repo_path / "configs" / "core-sw-par-01.conf", "hostname core-sw-par-01\n")
    _commit(repo_path, "Initial device configs")

    _write(
        repo_path / "configs" / "edge-fw-par-01.conf",
        "hostname edge-fw-par-01\nset ssh strong\nset psksecret supersecret\n",
    )
    _commit(repo_path, "Harden SSH on edge-fw-par-01")

    _write(
        repo_path / "configs" / "core-sw-par-01.conf",
        "hostname core-sw-par-01\nrouter bgp 65010\n",
    )
    _write(repo_path / "configs" / "dist-rtr-nyc-01.conf", "hostname dist-rtr-nyc-01\n")
    _commit(repo_path, "Tune core BGP and add dist-rtr-nyc-01")

    return repo_path


def test_clone_repo_and_list_devices(tmp_path: Path) -> None:
    source_repo = _build_source_repo(tmp_path)
    cloned_repo = tmp_path / "clone-repo"

    cloned = clone_repo(str(source_repo), cloned_repo)

    assert cloned["already_cloned"] is False
    assert Path(cloned["repo_path"]).exists()

    devices = list_device_files(cloned_repo)

    assert [item["device"] for item in devices] == [
        "core-sw-par-01",
        "dist-rtr-nyc-01",
        "edge-fw-par-01",
    ]


def test_get_device_file_info_returns_last_change_and_diff(tmp_path: Path) -> None:
    source_repo = _build_source_repo(tmp_path)

    info = get_device_file_info(source_repo, "edge-fw-par-01")

    assert info["device"] == "edge-fw-par-01"
    assert info["last_commit"]["message"] == "Harden SSH on edge-fw-par-01"
    assert "set ssh strong" in info["last_diff"]
    assert "set psksecret" not in info["last_diff"]
    assert "supersecret" not in info["last_diff"]
    assert info["commit_count"] == 2


def test_recent_commits_include_affected_devices(tmp_path: Path) -> None:
    source_repo = _build_source_repo(tmp_path)

    commits = get_recent_commits_with_devices(source_repo, limit=2)

    assert len(commits) == 2
    assert commits[0]["message"] == "Tune core BGP and add dist-rtr-nyc-01"
    assert commits[0]["affected_devices"] == ["core-sw-par-01", "dist-rtr-nyc-01"]
    assert commits[1]["affected_devices"] == ["edge-fw-par-01"]


def test_sanitize_config_text_covers_vendor_styles() -> None:
    raw = "\n".join(
        [
            "hostname edge-fw-par-01",
            "username admin secret 9 $9$abc123",
            'set system login user noc authentication encrypted-password "$6$hash"',
            "snmp-server community public ro",
            "modify auth user admin password supersecret",
            "rootpw=letmein",
            "shared-secret: keepme",
        ]
    )

    sanitized = sanitize_config_text(raw)

    assert "$9$abc123" not in sanitized
    assert "$6$hash" not in sanitized
    assert "public ro" not in sanitized
    assert "supersecret" not in sanitized
    assert "letmein" not in sanitized
    assert "keepme" not in sanitized
    assert "username admin secret" not in sanitized
    assert "hostname edge-fw-par-01" in sanitized
