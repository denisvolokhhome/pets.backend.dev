"""User manager for fastapi-users authentication system."""
import uuid
from typing import Optional

from fastapi import Request
from fastapi_users import BaseUserManager, UUIDIDMixin

from app.models.user import User
from app.config import Settings


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    Custom user manager for handling user lifecycle events.
    
    Extends fastapi-users BaseUserManager with custom hooks for:
    - User registration
    - Password reset requests
    - Email verification requests
    """
    
    def __init__(self, user_db, settings: Settings):
        """
        Initialize UserManager with user database and settings.
        
        Args:
            user_db: Database adapter for user operations
            settings: Application settings containing secrets
        """
        super().__init__(user_db)
        self.reset_password_token_secret = settings.secret_key
        self.verification_token_secret = settings.secret_key
        self.reset_password_token_lifetime_seconds = settings.jwt_lifetime_seconds
        self.verification_token_lifetime_seconds = settings.jwt_lifetime_seconds
    
    async def on_after_register(
        self, 
        user: User, 
        request: Optional[Request] = None
    ) -> None:
        """
        Hook called after successful user registration.
        
        Args:
            user: The newly registered user
            request: Optional request object
        """
        print(f"User {user.id} has registered with email {user.email}")
        # In production, this would send a welcome email or trigger other actions
    
    async def on_after_forgot_password(
        self,
        user: User,
        token: str,
        request: Optional[Request] = None
    ) -> None:
        """
        Hook called after password reset is requested.
        
        Args:
            user: The user requesting password reset
            token: The reset token
            request: Optional request object
        """
        print(f"User {user.id} has requested password reset. Token: {token}")
        # In production, this would send a password reset email
    
    async def on_after_request_verify(
        self,
        user: User,
        token: str,
        request: Optional[Request] = None
    ) -> None:
        """
        Hook called after email verification is requested.
        
        Args:
            user: The user requesting verification
            token: The verification token
            request: Optional request object
        """
        print(f"Verification requested for user {user.id}. Token: {token}")
        # In production, this would send a verification email
    
    async def validate_password(
        self,
        password: str,
        user: Optional[User] = None
    ) -> None:
        """
        Validate password meets security requirements.
        
        Args:
            password: The password to validate
            user: Optional user object for context
            
        Raises:
            InvalidPasswordException: If password doesn't meet requirements
        """
        # Minimum length check
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        # Maximum length check (prevent DoS)
        if len(password) > 100:
            raise ValueError("Password must be at most 100 characters long")
        
        # Check for at least one letter
        if not any(c.isalpha() for c in password):
            raise ValueError("Password must contain at least one letter")
        
        # Check for at least one digit
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")
        
        # Prevent password same as email
        if user and password.lower() == user.email.lower():
            raise ValueError("Password cannot be the same as email")
