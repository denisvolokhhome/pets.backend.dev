"""Integration tests for authentication endpoints.

Tests the complete authentication flow including:
- User registration
- Login and token generation
- Password reset flow
- Email verification flow
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session


@pytest.fixture
async def client(async_session: AsyncSession):
    """Create test client with database session override."""
    
    async def override_get_async_session():
        yield async_session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_user_registration_flow(client: AsyncClient):
    """
    Test complete user registration flow.
    
    Validates: Requirements 4.1, 4.2, 13.1
    """
    # Register a new user
    registration_data = {
        "email": "newuser@example.com",
        "password": "SecurePassword123!",
    }
    
    response = await client.post("/api/auth/register", json=registration_data)
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify response contains user data
    assert "id" in data
    assert data["email"] == registration_data["email"]
    assert data["is_active"] is True
    assert data["is_superuser"] is False
    assert data["is_verified"] is False
    assert "hashed_password" not in data  # Password should not be returned


@pytest.mark.asyncio
async def test_user_registration_duplicate_email(client: AsyncClient):
    """
    Test that registering with duplicate email fails.
    
    Validates: Requirements 4.1
    """
    registration_data = {
        "email": "duplicate@example.com",
        "password": "SecurePassword123!",
    }
    
    # Register first user
    response1 = await client.post("/api/auth/register", json=registration_data)
    assert response1.status_code == 201
    
    # Try to register with same email
    response2 = await client.post("/api/auth/register", json=registration_data)
    assert response2.status_code == 400
    
    data = response2.json()
    assert "detail" in data
    assert "REGISTER_USER_ALREADY_EXISTS" in data["detail"]


@pytest.mark.asyncio
async def test_user_registration_missing_password(client: AsyncClient):
    """
    Test that registration without password fails.
    
    Validates: Requirements 4.1
    """
    registration_data = {
        "email": "test@example.com",
        # Missing password
    }
    
    response = await client.post("/api/auth/register", json=registration_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_and_token_generation(client: AsyncClient):
    """
    Test login flow and JWT token generation.
    
    Validates: Requirements 4.2, 13.1
    """
    # First register a user
    registration_data = {
        "email": "loginuser@example.com",
        "password": "SecurePassword123!",
    }
    
    register_response = await client.post("/api/auth/register", json=registration_data)
    assert register_response.status_code == 201
    
    # Now login
    login_data = {
        "username": registration_data["email"],  # fastapi-users uses 'username' field
        "password": registration_data["password"],
    }
    
    login_response = await client.post(
        "/api/auth/jwt/login",
        data=login_data,  # Use form data for OAuth2 password flow
    )
    
    assert login_response.status_code == 200
    token_data = login_response.json()
    
    # Verify token response
    assert "access_token" in token_data
    assert "token_type" in token_data
    assert token_data["token_type"] == "bearer"
    
    # Verify token can be used to access protected endpoint
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_response = await client.get("/api/auth/users/me", headers=headers)
    
    assert me_response.status_code == 200
    user_data = me_response.json()
    assert user_data["email"] == registration_data["email"]


@pytest.mark.asyncio
async def test_login_with_invalid_credentials(client: AsyncClient):
    """
    Test that login with invalid credentials fails.
    
    Validates: Requirements 4.2
    """
    # Try to login with non-existent user
    login_data = {
        "username": "nonexistent@example.com",
        "password": "WrongPassword123!",
    }
    
    response = await client.post("/api/auth/jwt/login", data=login_data)
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "LOGIN_BAD_CREDENTIALS" in data["detail"]


@pytest.mark.asyncio
async def test_login_with_wrong_password(client: AsyncClient):
    """
    Test that login with wrong password fails.
    
    Validates: Requirements 4.2
    """
    # Register a user
    registration_data = {
        "email": "wrongpass@example.com",
        "password": "CorrectPassword123!",
    }
    
    register_response = await client.post("/api/auth/register", json=registration_data)
    assert register_response.status_code == 201
    
    # Try to login with wrong password
    login_data = {
        "username": registration_data["email"],
        "password": "WrongPassword123!",
    }
    
    response = await client.post("/api/auth/jwt/login", data=login_data)
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "LOGIN_BAD_CREDENTIALS" in data["detail"]


@pytest.mark.asyncio
async def test_logout_flow(client: AsyncClient):
    """
    Test logout flow.
    
    Validates: Requirements 4.2
    """
    # Register and login
    registration_data = {
        "email": "logoutuser@example.com",
        "password": "SecurePassword123!",
    }
    
    await client.post("/api/auth/register", json=registration_data)
    
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    login_response = await client.post("/api/auth/jwt/login", data=login_data)
    token_data = login_response.json()
    
    # Logout
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    logout_response = await client.post("/api/auth/jwt/logout", headers=headers)
    
    # JWT logout returns 204 No Content
    assert logout_response.status_code == 204


@pytest.mark.asyncio
async def test_password_reset_request_flow(client: AsyncClient):
    """
    Test password reset request flow.
    
    Validates: Requirements 4.2, 13.1
    """
    # Register a user
    registration_data = {
        "email": "resetpass@example.com",
        "password": "OldPassword123!",
    }
    
    register_response = await client.post("/api/auth/register", json=registration_data)
    assert register_response.status_code == 201
    
    # Request password reset
    reset_request_data = {
        "email": registration_data["email"],
    }
    
    response = await client.post("/api/auth/forgot-password", json=reset_request_data)
    
    # Should return 202 Accepted regardless of whether email exists (security)
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_password_reset_request_nonexistent_email(client: AsyncClient):
    """
    Test password reset request for non-existent email.
    
    Should return same response as valid email for security.
    
    Validates: Requirements 4.2
    """
    reset_request_data = {
        "email": "nonexistent@example.com",
    }
    
    response = await client.post("/api/auth/forgot-password", json=reset_request_data)
    
    # Should return 202 Accepted (don't reveal if email exists)
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_email_verification_request_flow(client: AsyncClient):
    """
    Test email verification request flow.
    
    Validates: Requirements 4.2, 13.1
    """
    # Register a user
    registration_data = {
        "email": "verifyemail@example.com",
        "password": "SecurePassword123!",
    }
    
    register_response = await client.post("/api/auth/register", json=registration_data)
    assert register_response.status_code == 201
    
    # Login to get token
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    login_response = await client.post("/api/auth/jwt/login", data=login_data)
    token_data = login_response.json()
    
    # Request verification email (requires email in body)
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    verify_request_data = {
        "email": registration_data["email"]
    }
    response = await client.post(
        "/api/auth/request-verify-token",
        json=verify_request_data,
        headers=headers
    )
    
    # Should return 202 Accepted
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """
    Test that protected endpoints require authentication.
    
    Validates: Requirements 3.5
    """
    # Try to access protected endpoint without token
    response = await client.get("/api/auth/users/me")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(client: AsyncClient):
    """
    Test that protected endpoints reject invalid tokens.
    
    Validates: Requirements 3.5
    """
    # Try to access protected endpoint with invalid token
    headers = {"Authorization": "Bearer invalid_token_here"}
    response = await client.get("/api/auth/users/me", headers=headers)
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """
    Test getting current authenticated user information.
    
    Validates: Requirements 4.2, 13.1
    """
    # Register and login
    registration_data = {
        "email": "currentuser@example.com",
        "password": "SecurePassword123!",
    }
    
    await client.post("/api/auth/register", json=registration_data)
    
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    login_response = await client.post("/api/auth/jwt/login", data=login_data)
    token_data = login_response.json()
    
    # Get current user
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    response = await client.get("/api/auth/users/me", headers=headers)
    
    assert response.status_code == 200
    user_data = response.json()
    
    assert user_data["email"] == registration_data["email"]
    assert "id" in user_data
    assert user_data["is_active"] is True
    assert "hashed_password" not in user_data


@pytest.mark.asyncio
async def test_update_current_user(client: AsyncClient):
    """
    Test updating current authenticated user information.
    
    Validates: Requirements 4.2, 13.1
    """
    # Register and login
    registration_data = {
        "email": "updateuser@example.com",
        "password": "SecurePassword123!",
    }
    
    await client.post("/api/auth/register", json=registration_data)
    
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    login_response = await client.post("/api/auth/jwt/login", data=login_data)
    token_data = login_response.json()
    
    # Update user
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    update_data = {
        "password": "NewSecurePassword123!",
    }
    
    response = await client.patch("/api/auth/users/me", json=update_data, headers=headers)
    
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == registration_data["email"]
    
    # Verify old password no longer works
    old_login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    old_login_response = await client.post("/api/auth/jwt/login", data=old_login_data)
    assert old_login_response.status_code == 400
    
    # Verify new password works
    new_login_data = {
        "username": registration_data["email"],
        "password": update_data["password"],
    }
    
    new_login_response = await client.post("/api/auth/jwt/login", data=new_login_data)
    assert new_login_response.status_code == 200
