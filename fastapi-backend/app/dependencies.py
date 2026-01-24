"""FastAPI dependencies for authentication and database access."""
import uuid
from typing import AsyncGenerator

from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.models.user import User
from app.services.user_manager import UserManager


# Initialize settings
settings = Settings()


async def get_user_db(
    session: AsyncSession = Depends(get_async_session)
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """
    Dependency to get the user database adapter.
    
    Args:
        session: Async database session
        
    Yields:
        SQLAlchemyUserDatabase: Database adapter for user operations
    """
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db)
) -> AsyncGenerator[UserManager, None]:
    """
    Dependency to get the user manager.
    
    Args:
        user_db: User database adapter
        
    Yields:
        UserManager: User manager instance
    """
    yield UserManager(user_db, settings)


def get_jwt_strategy() -> JWTStrategy:
    """
    Get JWT authentication strategy.
    
    Returns:
        JWTStrategy: JWT strategy configured with secret and lifetime
    """
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.jwt_lifetime_seconds,
        algorithm="HS256",
    )


# Configure Bearer token transport
bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


# Configure authentication backend with JWT
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# Create FastAPIUsers instance
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)


# Export commonly used dependencies
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
optional_current_user = fastapi_users.current_user(optional=True)
