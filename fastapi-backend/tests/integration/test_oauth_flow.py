"""Integration tests for OAuth registration flow."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.fixture
def mock_oauth_settings():
    """Mock OAuth settings to enable OAuth endpoints in tests."""
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.google_oauth_client_id = "test_client_id"
        mock_settings.google_oauth_client_secret = "test_client_secret"
        mock_settings.google_oauth_redirect_uri = "http://test/callback"
        yield mock_settings


class TestOAuthFlow:
    """Test OAuth registration and authentication flow."""
    
    @pytest.mark.asyncio
    async def test_google_oauth_authorization_url(
        self,
        unauthenticated_client: AsyncClient,
        mock_oauth_settings
    ):
        """
        Test that Google OAuth authorization URL is generated correctly.
        
        Requirements: 4.2
        """
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_authorization_url = AsyncMock(
                return_value="https://accounts.google.com/o/oauth2/auth?client_id=test"
            )
            
            response = await unauthenticated_client.get("/api/auth/google/authorize")
            
            assert response.status_code == 200
            data = response.json()
            assert "authorization_url" in data
            assert "accounts.google.com" in data["authorization_url"]
    
    @pytest.mark.asyncio
    async def test_google_oauth_callback_new_user(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        mock_oauth_settings
    ):
        """
        Test OAuth callback creates new pet seeker user.
        
        Requirements: 4.3, 4.5
        """
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        mock_user_info = {
            "email": "newuser@gmail.com",
            "name": "New User",
            "sub": "google_oauth_id_12345"
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(return_value=mock_user_info)
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_auth_code"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["user"]["email"] == "newuser@gmail.com"
            assert data["user"]["is_breeder"] is False
            
            # Verify user was created in database
            query = select(User).where(User.email == "newuser@gmail.com")
            result = await async_session.execute(query)
            user = result.scalar_one()
            
            assert user.email == "newuser@gmail.com"
            assert user.is_breeder is False
            assert user.oauth_provider == "google"
            assert user.oauth_id == "google_oauth_id_12345"
    
    @pytest.mark.asyncio
    async def test_google_oauth_callback_existing_user(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        mock_oauth_settings
    ):
        """
        Test OAuth callback authenticates existing pet seeker.
        
        Requirements: 4.4, 4.5
        """
        # Create existing OAuth user
        existing_user = User(
            email="existing@gmail.com",
            hashed_password="",
            name="Existing User",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
            oauth_provider="google",
            oauth_id="google_oauth_id_existing"
        )
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        mock_user_info = {
            "email": "existing@gmail.com",
            "name": "Existing User",
            "sub": "google_oauth_id_existing"
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(return_value=mock_user_info)
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_auth_code"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "access_token" in data
            assert data["user"]["email"] == "existing@gmail.com"
            assert data["user"]["is_breeder"] is False
            
            # Verify no duplicate user was created
            query = select(User).where(User.email == "existing@gmail.com")
            result = await async_session.execute(query)
            users = result.scalars().all()
            
            assert len(users) == 1
            assert users[0].id == existing_user.id
    
    @pytest.mark.asyncio
    async def test_google_oauth_callback_invalid_code(
        self,
        unauthenticated_client: AsyncClient,
        mock_oauth_settings
    ):
        """
        Test OAuth callback handles invalid authorization code.
        
        Requirements: 4.2, 4.3
        """
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(
                side_effect=Exception("Invalid authorization code")
            )
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=invalid_code"
            )
            
            assert response.status_code in [400, 502]
            data = response.json()
            assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_google_oauth_callback_provider_error(
        self,
        unauthenticated_client: AsyncClient,
        mock_oauth_settings
    ):
        """
        Test OAuth callback handles provider errors gracefully.
        
        Requirements: 4.2, 4.3
        """
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(
                side_effect=Exception("Provider error")
            )
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_code"
            )
            
            assert response.status_code in [400, 502]
            data = response.json()
            assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_oauth_user_is_pet_seeker(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        mock_oauth_settings
    ):
        """
        Test that OAuth registration always creates pet seeker accounts.
        
        Requirements: 3.5, 4.3
        """
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        mock_user_info = {
            "email": "petseeker@gmail.com",
            "name": "Pet Seeker",
            "sub": "google_oauth_id_petseeker"
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(return_value=mock_user_info)
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_code"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["user"]["is_breeder"] is False
            
            # Verify in database
            query = select(User).where(User.email == "petseeker@gmail.com")
            result = await async_session.execute(query)
            user = result.scalar_one()
            
            assert user.is_breeder is False
    
    @pytest.mark.asyncio
    async def test_oauth_callback_missing_code(
        self,
        unauthenticated_client: AsyncClient,
        mock_oauth_settings
    ):
        """
        Test OAuth callback requires authorization code parameter.
        
        Requirements: 4.2, 4.3
        """
        response = await unauthenticated_client.get("/api/auth/google/callback")
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_oauth_user_receives_jwt_token(
        self,
        unauthenticated_client: AsyncClient,
        mock_oauth_settings
    ):
        """
        Test that OAuth authentication returns valid JWT token.
        
        Requirements: 4.5
        """
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        mock_user_info = {
            "email": "jwttest@gmail.com",
            "name": "JWT Test",
            "sub": "google_oauth_id_jwt"
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(return_value=mock_user_info)
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_code"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "access_token" in data
            assert isinstance(data["access_token"], str)
            assert len(data["access_token"]) > 0
            assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_oauth_flow_end_to_end(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        mock_oauth_settings
    ):
        """
        Test complete OAuth flow from authorization to authentication.
        
        Requirements: 4.2, 4.3, 4.5
        """
        # Step 1: Get authorization URL
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_authorization_url = AsyncMock(
                return_value="https://accounts.google.com/o/oauth2/auth"
            )
            
            response = await unauthenticated_client.get("/api/auth/google/authorize")
            assert response.status_code == 200
            data = response.json()
            assert "authorization_url" in data
        
        # Step 2: Simulate OAuth callback
        mock_token_response = {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        mock_user_info = {
            "email": "e2etest@gmail.com",
            "name": "E2E Test User",
            "sub": "google_oauth_id_e2e"
        }
        
        with patch("app.routers.auth.google_oauth_client") as mock_oauth:
            mock_oauth.get_access_token = AsyncMock(return_value=mock_token_response)
            mock_oauth.get_id_email = AsyncMock(return_value=mock_user_info)
            
            response = await unauthenticated_client.get(
                "/api/auth/google/callback?code=mock_auth_code"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "access_token" in data
            
            # Verify user was created as pet seeker
            query = select(User).where(User.email == "e2etest@gmail.com")
            result = await async_session.execute(query)
            user = result.scalar_one()
            
            assert user.email == "e2etest@gmail.com"
            assert user.is_breeder is False
            assert user.oauth_provider == "google"
            assert user.is_active is True
