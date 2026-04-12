from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import User, get_current_user
from app.db.session import get_async_session

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
CheckUserSSODep = Annotated[User, Depends(get_current_user)]
