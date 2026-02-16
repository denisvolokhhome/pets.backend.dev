"""FastAPI dependencies for authentication and database access."""
import uuid
from typing import AsyncGenerator, Optional

from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.models.user import User
from app.services.user_manager import UserManager
from app.services.geocoding_service import GeocodingService


# Initialize settings
settings = Settings()


# Redis client singleton
_redis_client: Optional[Redis] = None


async def get_redis() -> Optional[Redis]:
    """
    Dependency to get Redis client for caching.
    
    Returns None if Redis connection fails (graceful degradation).
    
    Yields:
        Optional[Redis]: Redis client or None
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await _redis_client.ping()
        except Exception as e:
            # Log warning but don't fail - service works without cache
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            _redis_client = None
    
    return _redis_client


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


# Authorization dependencies for user type checking
def require_breeder(user: User = Depends(current_active_user)) -> User:
    """
    Dependency that ensures the current user is a breeder.
    
    Args:
        user: Current authenticated user
        
    Returns:
        User: The authenticated breeder user
        
    Raises:
        HTTPException: 403 Forbidden if user is not a breeder
    """
    from fastapi import HTTPException, status
    
    if not user.is_breeder:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Breeder access required"
        )
    return user


def require_pet_seeker(user: User = Depends(current_active_user)) -> User:
    """
    Dependency that ensures the current user is a pet seeker.
    
    Args:
        user: Current authenticated user
        
    Returns:
        User: The authenticated pet seeker user
        
    Raises:
        HTTPException: 403 Forbidden if user is a breeder
    """
    from fastapi import HTTPException, status
    
    if user.is_breeder:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pet seeker access required"
        )
    return user
