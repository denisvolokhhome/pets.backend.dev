"""Unit tests for authorization dependencies.

Tests edge cases for require_breeder and require_pet_seeker dependencies.
"""
import pytest
import uuid
from fastapi import HTTPException

from app.models.user import User
from app.dependencies import require_breeder, require_pet_seeker


class TestRequireBreederDependency:
    """Unit tests for require_breeder dependency function."""
    
    def test_breeder_user_passes_authorization(self):
        """Test that a breeder user passes require_breeder check."""
        # Create breeder user
        user = User(
            id=uuid.uuid4(),
            email="breeder@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        
        # Should not raise exception
        result = require_breeder(user)
        assert result == user
    
    def test_pet_seeker_user_fails_authorization(self):
        """Test that a pet seeker user fails require_breeder check."""
        # Create pet seeker user
        user = User(
            id=uuid.uuid4(),
            email="petseeker@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
        )
        
        # Should raise 403 exception
        with pytest.raises(HTTPException) as exc_info:
            require_breeder(user)
        
        assert exc_info.value.status_code == 403
        assert "Breeder access required" in str(exc_info.value.detail)
    
    def test_inactive_breeder_user_not_checked_by_dependency(self):
        """
        Test that inactive user status is not checked by require_breeder.
        
        Note: User activity is checked by current_active_user dependency,
        not by require_breeder. This test verifies require_breeder only
        checks is_breeder field.
        """
        # Create inactive breeder user
        user = User(
            id=uuid.uuid4(),
            email="inactive@example.com",
            hashed_password="hashed_password",
            is_active=False,  # Inactive
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        
        # require_breeder should still pass (activity checked elsewhere)
        result = require_breeder(user)
        assert result == user
    
    def test_unverified_breeder_user_not_checked_by_dependency(self):
        """
        Test that unverified user status is not checked by require_breeder.
        
        Note: Email verification is checked by authentication flow,
        not by require_breeder. This test verifies require_breeder only
        checks is_breeder field.
        """
        # Create unverified breeder user
        user = User(
            id=uuid.uuid4(),
            email="unverified@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=False,  # Not verified
            is_breeder=True,
        )
        
        # require_breeder should still pass (verification checked elsewhere)
        result = require_breeder(user)
        assert result == user


class TestRequirePetSeekerDependency:
    """Unit tests for require_pet_seeker dependency function."""
    
    def test_pet_seeker_user_passes_authorization(self):
        """Test that a pet seeker user passes require_pet_seeker check."""
        # Create pet seeker user
        user = User(
            id=uuid.uuid4(),
            email="petseeker@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
        )
        
        # Should not raise exception
        result = require_pet_seeker(user)
        assert result == user
    
    def test_breeder_user_fails_authorization(self):
        """Test that a breeder user fails require_pet_seeker check."""
        # Create breeder user
        user = User(
            id=uuid.uuid4(),
            email="breeder@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        
        # Should raise 403 exception
        with pytest.raises(HTTPException) as exc_info:
            require_pet_seeker(user)
        
        assert exc_info.value.status_code == 403
        assert "Pet seeker access required" in str(exc_info.value.detail)
    
    def test_inactive_pet_seeker_user_not_checked_by_dependency(self):
        """
        Test that inactive user status is not checked by require_pet_seeker.
        
        Note: User activity is checked by current_active_user dependency,
        not by require_pet_seeker. This test verifies require_pet_seeker only
        checks is_breeder field.
        """
        # Create inactive pet seeker user
        user = User(
            id=uuid.uuid4(),
            email="inactive@example.com",
            hashed_password="hashed_password",
            is_active=False,  # Inactive
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
        )
        
        # require_pet_seeker should still pass (activity checked elsewhere)
        result = require_pet_seeker(user)
        assert result == user


class TestAuthorizationErrorMessages:
    """Unit tests for authorization error message consistency."""
    
    def test_require_breeder_error_message_format(self):
        """Test that require_breeder returns consistent error message."""
        user = User(
            id=uuid.uuid4(),
            email="petseeker@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
        )
        
        with pytest.raises(HTTPException) as exc_info:
            require_breeder(user)
        
        # Verify error structure
        assert exc_info.value.status_code == 403
        assert isinstance(exc_info.value.detail, str)
        assert len(exc_info.value.detail) > 0
        assert "Breeder access required" == exc_info.value.detail
    
    def test_require_pet_seeker_error_message_format(self):
        """Test that require_pet_seeker returns consistent error message."""
        user = User(
            id=uuid.uuid4(),
            email="breeder@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        
        with pytest.raises(HTTPException) as exc_info:
            require_pet_seeker(user)
        
        # Verify error structure
        assert exc_info.value.status_code == 403
        assert isinstance(exc_info.value.detail, str)
        assert len(exc_info.value.detail) > 0
        assert "Pet seeker access required" == exc_info.value.detail


class TestAuthorizationEdgeCases:
    """Unit tests for authorization edge cases."""
    
    def test_superuser_breeder_passes_require_breeder(self):
        """Test that superuser breeders can access breeder endpoints."""
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=True,  # Superuser
            is_verified=True,
            is_breeder=True,
        )
        
        result = require_breeder(user)
        assert result == user
    
    def test_superuser_pet_seeker_fails_require_breeder(self):
        """
        Test that superuser status doesn't bypass user type check.
        
        Even superusers must have is_breeder=True to access breeder endpoints.
        """
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=True,  # Superuser
            is_verified=True,
            is_breeder=False,  # But not a breeder
        )
        
        # Should still fail authorization
        with pytest.raises(HTTPException) as exc_info:
            require_breeder(user)
        
        assert exc_info.value.status_code == 403
