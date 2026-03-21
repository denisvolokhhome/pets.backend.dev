"""User manager for fastapi-users authentication system."""
import uuid
import logging
from typing import Optional

from fastapi import Request
from fastapi_users import BaseUserManager, UUIDIDMixin

from app.models.user import User
from app.config import Settings
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    Custom user manager for handling user lifecycle events.

    Extends fastapi-users BaseUserManager with email-powered hooks for:
    - User registration (welcome email)
    - Password reset requests
    - Email verification requests
    """

    def __init__(self, user_db, settings: Settings):
        super().__init__(user_db)
        self.settings = settings
        self.reset_password_token_secret = settings.secret_key
        self.verification_token_secret = settings.secret_key
        self.reset_password_token_lifetime_seconds = 3600  # 1 hour
        self.verification_token_lifetime_seconds = settings.jwt_lifetime_seconds
        self.email_service = EmailService(settings)

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        logger.info("User %s registered with email %s", user.id, user.email)
        await self.email_service.send_welcome(
            to=user.email, name=user.name or user.email
        )

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        logger.info("Password reset requested for user %s", user.id)
        await self.email_service.send_password_reset(
            to=user.email,
            token=token,
            frontend_url=self.settings.frontend_url,
        )

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        logger.info("Verification requested for user %s", user.id)
        # Future: send verification email

    async def validate_password(
        self, password: str, user: Optional[User] = None
    ) -> None:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(password) > 100:
            raise ValueError("Password must be at most 100 characters long")
        if not any(c.isalpha() for c in password):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")
        if user and password.lower() == user.email.lower():
            raise ValueError("Password cannot be the same as email")
