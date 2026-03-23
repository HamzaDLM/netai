from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.db.session import get_async_session
from app.core.security import User, get_current_user

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
CheckUserSSODep = Annotated[User, Depends(get_current_user)]
