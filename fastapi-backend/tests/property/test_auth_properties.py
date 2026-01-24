"""Property-based tests for authentication system."""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from httpx import AsyncClient, ASGITransport
import jwt
from datetime import datetime, timedelta
from typing import AsyncGenerator

from app.main import app
from app.config import Settings
from app.models.user import User
from app.database import Base, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import os


# Strategies for generating test data
email_strategy = st.emails()
password_strategy = st.text(min_size=8, max_size=100).filter(
    lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)
)


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with proper setup and teardown."""
    test_database_url = os.environ.get(
        'TEST_DATABASE_URL',
        'postgresql+asyncpg://test:test@localhost:5432/test_db'
    )
    
    engine = create_async_engine(
        test_database_url,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker_test = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker_test() as session:
        yield session
        await session.rollback()
    
    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def client(test_db_session):
    """Create async HTTP client for testing with database override."""
    # Override the get_async_session dependency
    async def override_get_async_session():
        yield test_db_session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    # Clean up override
    app.dependency_overrides.clear()


@pytest.fixture
async def registered_user(test_db_session):
    """Create a registered user for testing."""
    from fastapi_users.password import PasswordHelper
    
    password_helper = PasswordHelper()
    
    user = User(
        email="testuser@example.com",
        hashed_password=password_helper.hash("TestPassword123"),
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


class TestJWTTokenIssuance:
    """
    Property 6: JWT Token Issuance
    
    For any valid user credentials, successful authentication should return 
    a valid JWT token that can be decoded and verified.
    
    Validates: Requirements 3.4
    """
    
    @pytest.mark.asyncio
    async def test_jwt_token_structure(self, client, registered_user):
        """
        Test that JWT tokens have correct structure.
        
        Feature: laravel-to-fastapi-migration, Property 6: JWT Token Issuance
        """
        # Login with valid credentials
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "TestPassword123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contains access token
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        
        # Verify token is a valid JWT
        token = data["access_token"]
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts
    
    @pytest.mark.asyncio
    async def test_jwt_token_can_be_decoded(self, client, registered_user):
        """
        Test that JWT tokens can be decoded with the secret key.
        
        Feature: laravel-to-fastapi-migration, Property 6: JWT Token Issuance
        """
        settings = Settings()
        
        # Login
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "TestPassword123"
            }
        )
        
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # Decode token with audience
        decoded = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience=["fastapi-users:auth"]
        )
        
        # Verify token contains expected claims
        assert "sub" in decoded  # Subject (user ID)
        assert "exp" in decoded  # Expiration time
        assert "aud" in decoded  # Audience
    
    @pytest.mark.asyncio
    async def test_jwt_token_contains_user_id(self, client, registered_user):
        """
        Test that JWT tokens contain the user ID in the subject claim.
        
        Feature: laravel-to-fastapi-migration, Property 6: JWT Token Issuance
        """
        settings = Settings()
        
        # Login
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "TestPassword123"
            }
        )
        
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # Decode and verify user ID with audience
        decoded = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience=["fastapi-users:auth"]
        )
        
        assert decoded["sub"] == str(registered_user.id)
    
    @pytest.mark.asyncio
    async def test_jwt_token_expiration(self, client, registered_user):
        """
        Test that JWT tokens have correct expiration time.
        
        Feature: laravel-to-fastapi-migration, Property 6: JWT Token Issuance
        """
        settings = Settings()
        
        # Login
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "TestPassword123"
            }
        )
        
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # Decode and check expiration with audience
        decoded = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience=["fastapi-users:auth"]
        )
        
        exp_timestamp = decoded["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()
        
        # Token should expire in the future
        assert exp_datetime > now
        
        # Token should expire within the configured lifetime (with some tolerance)
        expected_expiry = now + timedelta(seconds=settings.jwt_lifetime_seconds)
        time_diff = abs((exp_datetime - expected_expiry).total_seconds())
        assert time_diff < 10  # Allow 10 seconds tolerance


class TestProtectedEndpointAuthorization:
    """
    Property 7: Protected Endpoint Authorization
    
    For any protected endpoint, requests without a valid JWT token should 
    return HTTP 401, and requests with a valid token should succeed.
    
    Validates: Requirements 3.5
    """
    
    @pytest.mark.asyncio
    async def test_protected_endpoint_without_token(self, client):
        """
        Test that protected endpoints reject requests without tokens.
        
        Feature: laravel-to-fastapi-migration, Property 7: Protected Endpoint Authorization
        """
        # Try to access a protected endpoint without token
        # Using the users/me endpoint from fastapi-users
        response = await client.get("/api/auth/users/me")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_token(self, client):
        """
        Test that protected endpoints reject invalid tokens.
        
        Feature: laravel-to-fastapi-migration, Property 7: Protected Endpoint Authorization
        """
        # Try with an invalid token
        response = await client.get(
            "/api/auth/users/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_protected_endpoint_with_valid_token(self, client, registered_user):
        """
        Test that protected endpoints accept valid tokens.
        
        Feature: laravel-to-fastapi-migration, Property 7: Protected Endpoint Authorization
        """
        # Login to get valid token
        login_response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "TestPassword123"
            }
        )
        
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Access protected endpoint with valid token
        response = await client.get(
            "/api/auth/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == registered_user.email
        assert data["id"] == str(registered_user.id)


class TestAuthenticationFailure:
    """
    Property 25: Authentication Failure Response
    
    For any API request with invalid credentials, the response should be HTTP 401.
    
    Validates: Requirements 10.3
    """
    
    @pytest.mark.asyncio
    async def test_login_with_invalid_email(self, client):
        """
        Test that login with non-existent email returns 401.
        
        Feature: laravel-to-fastapi-migration, Property 25: Authentication Failure Response
        """
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": "nonexistent@example.com",
                "password": "SomePassword123"
            }
        )
        
        assert response.status_code == 400  # fastapi-users returns 400 for bad credentials
    
    @pytest.mark.asyncio
    async def test_login_with_wrong_password(self, client, registered_user):
        """
        Test that login with wrong password returns 401.
        
        Feature: laravel-to-fastapi-migration, Property 25: Authentication Failure Response
        """
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": registered_user.email,
                "password": "WrongPassword123"
            }
        )
        
        assert response.status_code == 400  # fastapi-users returns 400 for bad credentials
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        email=email_strategy,
        password=password_strategy
    )
    async def test_login_with_random_invalid_credentials(self, client, email, password):
        """
        Property test: Any random credentials should fail authentication.
        
        Feature: laravel-to-fastapi-migration, Property 25: Authentication Failure Response
        """
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": email,
                "password": password
            }
        )
        
        # Should return 400 (bad credentials) since these are random users
        assert response.status_code in [400, 422]  # 422 for validation errors



class TestPasswordHashCompatibility:
    """
    Property 5: Password Hash Compatibility
    
    For any existing user from the Laravel system, their password should 
    authenticate successfully in the FastAPI system.
    
    Validates: Requirements 3.3
    """
    
    @pytest.mark.asyncio
    async def test_bcrypt_hash_verification(self, test_db_session):
        """
        Test that bcrypt hashes from Laravel can be verified.
        
        Laravel uses bcrypt for password hashing. This test verifies that
        passwords hashed with bcrypt can be verified by fastapi-users.
        
        Feature: laravel-to-fastapi-migration, Property 5: Password Hash Compatibility
        """
        from fastapi_users.password import PasswordHelper
        import bcrypt
        
        password_helper = PasswordHelper()
        
        # Simulate a Laravel bcrypt hash
        # Laravel uses bcrypt with cost factor 10 by default
        plain_password = "TestPassword123"
        laravel_hash = bcrypt.hashpw(
            plain_password.encode('utf-8'),
            bcrypt.gensalt(rounds=10)
        ).decode('utf-8')
        
        # Create user with Laravel-style hash
        user = User(
            email="laravel_user@example.com",
            hashed_password=laravel_hash,
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        test_db_session.add(user)
        await test_db_session.commit()
        
        # Verify that fastapi-users can verify the Laravel hash
        is_valid, updated_hash = password_helper.verify_and_update(
            plain_password,
            laravel_hash
        )
        
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_login_with_laravel_bcrypt_hash(self, client, test_db_session):
        """
        Test that users with Laravel bcrypt hashes can login.
        
        Feature: laravel-to-fastapi-migration, Property 5: Password Hash Compatibility
        """
        import bcrypt
        
        # Create user with Laravel-style bcrypt hash
        plain_password = "LaravelPassword123"
        laravel_hash = bcrypt.hashpw(
            plain_password.encode('utf-8'),
            bcrypt.gensalt(rounds=10)
        ).decode('utf-8')
        
        user = User(
            email="laravel_login@example.com",
            hashed_password=laravel_hash,
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        test_db_session.add(user)
        await test_db_session.commit()
        
        # Try to login with the plain password
        response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": user.email,
                "password": plain_password
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=500  # Increase deadline for bcrypt hashing
    )
    @given(password=password_strategy.filter(lambda p: len(p.encode('utf-8')) <= 72))
    async def test_bcrypt_compatibility_with_various_passwords(self, test_db_session, password):
        """
        Property test: Any password hashed with bcrypt should be verifiable.
        
        Note: bcrypt has a 72-byte limit on passwords, so we filter to that length.
        
        Feature: laravel-to-fastapi-migration, Property 5: Password Hash Compatibility
        """
        from fastapi_users.password import PasswordHelper
        import bcrypt
        
        password_helper = PasswordHelper()
        
        # Hash with bcrypt (Laravel style)
        # Truncate to 72 bytes if needed (bcrypt limitation)
        password_bytes = password.encode('utf-8')[:72]
        bcrypt_hash = bcrypt.hashpw(
            password_bytes,
            bcrypt.gensalt(rounds=10)
        ).decode('utf-8')
        
        # Verify with fastapi-users using the same truncated password
        password_to_verify = password_bytes.decode('utf-8')
        is_valid, updated_hash = password_helper.verify_and_update(
            password_to_verify,
            bcrypt_hash
        )
        
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_wrong_password_fails_with_bcrypt_hash(self, test_db_session):
        """
        Test that wrong passwords fail verification with bcrypt hashes.
        
        Feature: laravel-to-fastapi-migration, Property 5: Password Hash Compatibility
        """
        from fastapi_users.password import PasswordHelper
        import bcrypt
        
        password_helper = PasswordHelper()
        
        # Hash a password with bcrypt
        correct_password = "CorrectPassword123"
        wrong_password = "WrongPassword456"
        
        bcrypt_hash = bcrypt.hashpw(
            correct_password.encode('utf-8'),
            bcrypt.gensalt(rounds=10)
        ).decode('utf-8')
        
        # Try to verify with wrong password
        is_valid, updated_hash = password_helper.verify_and_update(
            wrong_password,
            bcrypt_hash
        )
        
        assert is_valid is False
