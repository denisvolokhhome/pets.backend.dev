"""Authentication routes using fastapi-users."""
from fastapi import APIRouter

from app.dependencies import auth_backend, fastapi_users
from app.schemas.user import UserRead, UserCreate, UserUpdate


# Create router for authentication endpoints
router = APIRouter()

# Include auth router for JWT login/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)

# Include register router
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"],
)

# Include reset password router
router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)

# Include verify router
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    tags=["auth"],
)

# Include users router (for /users/me endpoint)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
