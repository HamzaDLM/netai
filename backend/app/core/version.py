import os
import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_backend_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception:
        pass
    return "unknown"


def get_backend_git_sha() -> str:
    return os.getenv("BACKEND_GIT_SHA", "dev").strip() or "dev"
