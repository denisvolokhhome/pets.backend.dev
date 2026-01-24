"""Unit tests for UserManager."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.user_manager import UserManager
from app.models.user import User
from app.config import Settings


@pytest.fixture
def mock_user_db():
    """Create a mock user database."""
    return AsyncMock()


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings()


@pytest.fixture
def user_manager(mock_user_db, settings):
    """Create UserManager instance for testing."""
    return UserManager(mock_user_db, settings)


@pytest.fixture
def test_user_obj():
    """Create a test user object."""
    return User(
        email="test@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )


class TestUserManagerHooks:
    """Test UserManager lifecycle hooks."""
    
    @pytest.mark.asyncio
    async def test_on_after_register(self, user_manager, test_user_obj, capsys):
        """Test that on_after_register hook is called after registration."""
        await user_manager.on_after_register(test_user_obj)
        
        captured = capsys.readouterr()
        assert f"User {test_user_obj.id} has registered" in captured.out
        assert test_user_obj.email in captured.out
    
    @pytest.mark.asyncio
    async def test_on_after_forgot_password(self, user_manager, test_user_obj, capsys):
        """Test that on_after_forgot_password hook is called."""
        token = "test_reset_token"
        await user_manager.on_after_forgot_password(test_user_obj, token)
        
        captured = capsys.readouterr()
        assert f"User {test_user_obj.id} has requested password reset" in captured.out
        assert token in captured.out
    
    @pytest.mark.asyncio
    async def test_on_after_request_verify(self, user_manager, test_user_obj, capsys):
        """Test that on_after_request_verify hook is called."""
        token = "test_verification_token"
        await user_manager.on_after_request_verify(test_user_obj, token)
        
        captured = capsys.readouterr()
        assert f"Verification requested for user {test_user_obj.id}" in captured.out
        assert token in captured.out


class TestPasswordValidation:
    """Test password validation logic."""
    
    @pytest.mark.asyncio
    async def test_validate_password_too_short(self, user_manager):
        """Test that passwords shorter than 8 characters are rejected."""
        with pytest.raises(ValueError, match="at least 8 characters"):
            await user_manager.validate_password("short1")
    
    @pytest.mark.asyncio
    async def test_validate_password_too_long(self, user_manager):
        """Test that passwords longer than 100 characters are rejected."""
        long_password = "a" * 101
        with pytest.raises(ValueError, match="at most 100 characters"):
            await user_manager.validate_password(long_password)
    
    @pytest.mark.asyncio
    async def test_validate_password_no_letters(self, user_manager):
        """Test that passwords without letters are rejected."""
        with pytest.raises(ValueError, match="at least one letter"):
            await user_manager.validate_password("12345678")
    
    @pytest.mark.asyncio
    async def test_validate_password_no_digits(self, user_manager):
        """Test that passwords without digits are rejected."""
        with pytest.raises(ValueError, match="at least one digit"):
            await user_manager.validate_password("abcdefgh")
    
    @pytest.mark.asyncio
    async def test_validate_password_same_as_email(self, user_manager):
        """Test that password cannot be the same as email."""
        # Create a user with an email that would pass other validations
        user = User(
            email="test123@example.com",  # Contains digits
            hashed_password="hashed",
            is_active=True
        )
        with pytest.raises(ValueError, match="cannot be the same as email"):
            await user_manager.validate_password("test123@example.com", user)
    
    @pytest.mark.asyncio
    async def test_validate_password_valid(self, user_manager):
        """Test that valid passwords pass validation."""
        # Should not raise any exception
        await user_manager.validate_password("ValidPass123")
        await user_manager.validate_password("AnotherGood1")
        await user_manager.validate_password("Test1234")
    
    @pytest.mark.asyncio
    async def test_validate_password_edge_cases(self, user_manager):
        """Test password validation edge cases."""
        # Exactly 8 characters with letter and digit
        await user_manager.validate_password("abcdef12")
        
        # Exactly 100 characters
        valid_100_char = "a" * 99 + "1"
        await user_manager.validate_password(valid_100_char)
        
        # Mixed case and special characters
        await user_manager.validate_password("P@ssw0rd!")
        await user_manager.validate_password("MyP@ss123")


class TestUserManagerConfiguration:
    """Test UserManager configuration."""
    
    def test_user_manager_initialization(self, mock_user_db, settings):
        """Test that UserManager is initialized with correct settings."""
        manager = UserManager(mock_user_db, settings)
        
        assert manager.reset_password_token_secret == settings.secret_key
        assert manager.verification_token_secret == settings.secret_key
        assert manager.reset_password_token_lifetime_seconds == settings.jwt_lifetime_seconds
        assert manager.verification_token_lifetime_seconds == settings.jwt_lifetime_seconds
