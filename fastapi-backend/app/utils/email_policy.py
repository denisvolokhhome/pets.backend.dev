"""Environment-dependent email address rules.

Production: sign-up uses the same strict rules as pydantic's EmailStr (used by fastapi-users
for forgot-password / verification), so every address that can register can also reset its
password. Reserved and special-use domains such as ``.test``, ``.local`` or ``.invalid`` are
rejected.

Other environments: sign-up stays permissive, and EmailStr is relaxed to accept ``.test``
domains so QA accounts like ``someone@example.test`` work end-to-end, including password reset.
"""
import email_validator
from email_validator import EmailNotValidError, validate_email

from app.config import Settings

_settings = Settings()

INVALID_EMAIL_MESSAGE = "Please enter a valid email address."


def apply_email_validator_environment() -> None:
    """Allow `.test` domains in EmailStr outside production (call once at startup)."""
    email_validator.TEST_ENVIRONMENT = not _settings.is_production


def validate_signup_email(value: str) -> str:
    """Pydantic field validator body for sign-up email fields."""
    if _settings.is_production:
        try:
            validate_email(value, check_deliverability=False, test_environment=False)
        except EmailNotValidError:
            raise ValueError(INVALID_EMAIL_MESSAGE)
    return value
