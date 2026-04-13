from fastapi import APIRouter

from app.core.version import get_backend_git_sha, get_backend_version

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/version")
def get_version() -> dict[str, str]:
    return {
        "backend_version": get_backend_version(),
        "backend_git_sha": get_backend_git_sha(),
    }
