"""Unit tests for OAuth error handling.

Tests OAuth provider errors, invalid authorization codes, and state mismatch scenarios.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import HTTPException

from app.main import app
from app.config import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings with OAuth configuration."""
    settings = Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test_db",
        secret_key="test_secret_key_at_least_32_characters_long",
        google_oauth_client_id="test_client_id",
        google_oauth_client_secret="test_client_secret",
        google_oauth_redirect_uri="http://localhost:8000/api/auth/google/callback",
    )
    return settings


@pytest.fixture
async def client():
    """Create async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestOAuthAuthorizationEndpoint:
    """Test OAuth authorization endpoint error handling."""
    
    @pytest.mark.asyncio
    async def test_authorize_without_oauth_config(self, client):
        """
        Test that authorization endpoint returns 503 when OAuth is not configured.
        
        Validates: Requirements 4.2
        """
        # Mock settings without OAuth credentials
        with patch('app.routers.auth.settings') as mock_settings:
            mock_settings.google_oauth_client_id = ""
            mock_settings.google_oauth_client_secret = ""
            
            response = await client.get("/api/auth/google/authorize")
            
            assert response.status_code == 503, \
                "Should return 503 when OAuth is not configured"
            assert "not configured" in response.json()["detail"].lower(), \
                "Error message should indicate OAuth is not configured"
    
    
    @pytest.mark.asyncio
    async def test_authorize_with_valid_config(self, client, mock_settings):
        """
        Test that authorization endpoint returns URL when properly configured.
        
        Validates: Requirements 4.2
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_authorization_url = AsyncMock(
                    return_value="https://accounts.google.com/o/oauth2/auth?..."
                )
                
                response = await client.get("/api/auth/google/authorize")
                
                assert response.status_code == 200, \
                    "Should return 200 when OAuth is configured"
                assert "authorization_url" in response.json(), \
                    "Response should contain authorization_url"
                assert response.json()["authorization_url"].startswith("https://"), \
                    "Authorization URL should be HTTPS"


class TestOAuthCallbackEndpoint:
    """Test OAuth callback endpoint error handling."""
    
    @pytest.mark.asyncio
    async def test_callback_without_oauth_config(self, client):
        """
        Test that callback returns 503 when OAuth is not configured.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings') as mock_settings:
            mock_settings.google_oauth_client_id = ""
            mock_settings.google_oauth_client_secret = ""
            
            response = await client.get("/api/auth/google/callback?code=test_code")
            
            assert response.status_code == 503, \
                "Should return 503 when OAuth is not configured"
            assert "not configured" in response.json()["detail"].lower(), \
                "Error message should indicate OAuth is not configured"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_invalid_code(self, client, mock_settings):
        """
        Test that callback handles invalid authorization code gracefully.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                # Simulate OAuth provider error for invalid code
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("Invalid authorization code")
                )
                
                response = await client.get("/api/auth/google/callback?code=invalid_code", follow_redirects=False)
                
                assert response.status_code == 307, \
                    "Should redirect for invalid authorization code"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_oauth_provider_error(self, client, mock_settings):
        """
        Test that callback handles OAuth provider errors gracefully.
        
        Validates: Requirements 4.2, 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                # Simulate OAuth provider error
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("OAuth provider temporarily unavailable")
                )
                
                response = await client.get("/api/auth/google/callback?code=test_code", follow_redirects=False)
                
                assert response.status_code == 307, \
                    "Should redirect for OAuth provider errors"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_network_error(self, client, mock_settings):
        """
        Test that callback handles network errors when contacting OAuth provider.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                # Simulate network error
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("Network connection failed")
                )
                
                response = await client.get("/api/auth/google/callback?code=test_code", follow_redirects=False)
                
                assert response.status_code == 307, \
                    "Should redirect for network errors"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_invalid_token_response(self, client, mock_settings):
        """
        Test that callback handles invalid token response from OAuth provider.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                # Simulate invalid token response
                mock_oauth.get_access_token = AsyncMock(
                    return_value={"invalid": "response"}
                )
                mock_oauth.get_id_email = AsyncMock(
                    side_effect=KeyError("access_token")
                )
                
                response = await client.get("/api/auth/google/callback?code=test_code", follow_redirects=False)
                
                assert response.status_code == 307, \
                    "Should redirect for invalid token response"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_missing_code_parameter(self, client, mock_settings):
        """
        Test that callback requires code parameter.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            response = await client.get("/api/auth/google/callback")
            
            # FastAPI will return 422 for missing required query parameter
            assert response.status_code == 422, \
                "Should return 422 for missing code parameter"


class TestOAuthStateValidation:
    """Test OAuth state parameter validation (CSRF protection)."""
    
    @pytest.mark.asyncio
    async def test_state_mismatch_scenario(self, client, mock_settings):
        """
        Test handling of state mismatch (potential CSRF attack).
        
        Note: Current implementation doesn't use state parameter.
        This test documents the expected behavior if state validation is added.
        
        Validates: Requirements 4.2
        """
        # This test documents expected behavior for future state validation
        # Current implementation doesn't validate state parameter
        # If state validation is added, this test should be updated
        
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    return_value={"access_token": "test_token"}
                )
                mock_oauth.get_id_email = AsyncMock(
                    return_value=("oauth_id_123", "test@example.com")
                )
                
                # Call with state parameter (currently ignored)
                response = await client.get(
                    "/api/auth/google/callback?code=test_code&state=invalid_state",
                    follow_redirects=False
                )
                
                # Current implementation doesn't validate state
                # OAuth flow redirects to frontend regardless
                assert response.status_code == 307, \
                    "OAuth callback redirects to frontend"


class TestOAuthUserCreationErrors:
    """Test error handling during OAuth user creation."""
    
    @pytest.mark.asyncio
    async def test_callback_with_database_error(self, client, mock_settings):
        """
        Test that callback handles database errors during user creation.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    return_value={"access_token": "test_token"}
                )
                mock_oauth.get_id_email = AsyncMock(
                    return_value=("oauth_id_123", "test@example.com")
                )
                
                # Mock database session to raise error
                with patch('app.routers.auth.get_async_session') as mock_session:
                    mock_db = AsyncMock()
                    mock_db.execute = AsyncMock(
                        side_effect=Exception("Database connection failed")
                    )
                    mock_session.return_value = mock_db
                    
                    response = await client.get("/api/auth/google/callback?code=test_code", follow_redirects=False)
                    
                    assert response.status_code == 307, \
                        "Should redirect for database errors"
                    assert "error=oauth_failed" in response.headers["location"], \
                        "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_invalid_email_from_provider(self, client, mock_settings):
        """
        Test that callback handles invalid email from OAuth provider.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    return_value={"access_token": "test_token"}
                )
                # Return invalid email format
                mock_oauth.get_id_email = AsyncMock(
                    return_value=("oauth_id_123", "not_an_email")
                )
                
                response = await client.get("/api/auth/google/callback?code=test_code", follow_redirects=False)
                
                # Should fail during user creation due to email validation
                assert response.status_code == 307, \
                    "Should redirect for invalid email from provider"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"


class TestOAuthSecurityScenarios:
    """Test OAuth security scenarios and edge cases."""
    
    @pytest.mark.asyncio
    async def test_callback_with_empty_code(self, client, mock_settings):
        """
        Test that callback rejects empty authorization code.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("Invalid code")
                )
                
                response = await client.get("/api/auth/google/callback?code=", follow_redirects=False)
                
                # Should redirect with error for empty code
                assert response.status_code == 307, \
                    "Should redirect for empty authorization code"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_malformed_code(self, client, mock_settings):
        """
        Test that callback handles malformed authorization codes.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("Invalid code format")
                )
                
                response = await client.get(
                    "/api/auth/google/callback?code=malformed<>code",
                    follow_redirects=False
                )
                
                assert response.status_code == 307, \
                    "Should redirect for malformed code"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
    
    
    @pytest.mark.asyncio
    async def test_callback_with_expired_code(self, client, mock_settings):
        """
        Test that callback handles expired authorization codes.
        
        Validates: Requirements 4.3
        """
        with patch('app.routers.auth.settings', mock_settings):
            with patch('app.routers.auth.google_oauth_client') as mock_oauth:
                mock_oauth.get_access_token = AsyncMock(
                    side_effect=Exception("Authorization code expired")
                )
                
                response = await client.get("/api/auth/google/callback?code=expired_code", follow_redirects=False)
                
                assert response.status_code == 307, \
                    "Should redirect for expired code"
                assert "error=oauth_failed" in response.headers["location"], \
                    "Redirect should include error parameter"
