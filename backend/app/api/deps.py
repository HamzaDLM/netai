from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import User, get_current_user
from app.db.session import get_async_session
from app.services.chat_runs import ChatRunCoordinator
from app.services.evals import EvalService
from app.services.netai import NetAIService


def get_netai_service(request: Request) -> NetAIService:
    service = getattr(request.app.state, "netai_service", None)
    if not isinstance(service, NetAIService):
        raise RuntimeError("NetAIService is unavailable outside the FastAPI lifespan")
    return service


def get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "")) or "unknown"


def get_eval_service(request: Request) -> EvalService:
    service = getattr(request.app.state, "eval_service", None)
    if not isinstance(service, EvalService):
        raise RuntimeError("EvalService is unavailable outside the FastAPI lifespan")
    return service


def get_chat_run_coordinator(request: Request) -> ChatRunCoordinator:
    coordinator = getattr(request.app.state, "chat_run_coordinator", None)
    if not isinstance(coordinator, ChatRunCoordinator):
        raise RuntimeError(
            "ChatRunCoordinator is unavailable outside the FastAPI lifespan"
        )
    return coordinator


AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
CheckUserSSODep = Annotated[User, Depends(get_current_user)]
NetAIServiceDep = Annotated[NetAIService, Depends(get_netai_service)]
EvalServiceDep = Annotated[EvalService, Depends(get_eval_service)]
ChatRunCoordinatorDep = Annotated[ChatRunCoordinator, Depends(get_chat_run_coordinator)]
RequestIDDep = Annotated[str, Depends(get_request_id)]
