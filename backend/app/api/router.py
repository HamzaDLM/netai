from fastapi import APIRouter

from app.api.endpoints import agent, chat, items
from app.core.config import project_settings

api_router = APIRouter()
api_router.include_router(items.router)
api_router.include_router(agent.router)
api_router.include_router(chat.router)

if project_settings.ENVIRONMENT == "local":
    # api_router.include_router(private.router)
    pass
