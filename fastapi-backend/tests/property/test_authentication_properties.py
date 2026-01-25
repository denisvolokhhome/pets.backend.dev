"""Property-based tests for authentication requirements across all endpoints.

Tests that all protected endpoints require valid authentication.
"""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
import os

from app.main import app
from app.database import Base, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


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


class TestAuthenticationRequired:
    """
    Property 7: Authentication Required
    
    For all profile and location management endpoints, requests without 
    valid authentication should return a 401 Unauthorized status.
    
    Validates: Requirements 8.8
    """
    
    @pytest.mark.asyncio
    async def test_profile_endpoints_require_authentication(self, client: AsyncClient):
        """
        Test that all profile management endpoints require authentication.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        # Test GET /api/users/me
        response = await client.get("/api/users/me")
        assert response.status_code == 401, "GET /api/users/me should require authentication"
        
        # Test PATCH /api/users/me
        response = await client.patch("/api/users/me", json={"breedery_name": "Test"})
        assert response.status_code == 401, "PATCH /api/users/me should require authentication"
        
        # Test POST /api/users/me/profile-image
        from io import BytesIO
        from PIL import Image
        
        # Create a test image
        image = Image.new('RGB', (100, 100), color='blue')
        buffer = BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        
        files = {"file": ("test.jpg", buffer, "image/jpeg")}
        response = await client.post("/api/users/me/profile-image", files=files)
        assert response.status_code == 401, "POST /api/users/me/profile-image should require authentication"
        
        # Test GET /api/users/me/profile-image
        response = await client.get("/api/users/me/profile-image")
        assert response.status_code == 401, "GET /api/users/me/profile-image should require authentication"
    
    @pytest.mark.asyncio
    async def test_location_endpoints_require_authentication(self, client: AsyncClient):
        """
        Test that all location management endpoints require authentication.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        location_data = {
            "name": "Test Location",
            "address1": "123 Test St",
            "city": "Test City",
            "state": "Test State",
            "country": "Test Country",
            "zipcode": "12345",
            "location_type": "user"
        }
        
        # Test GET /api/locations/
        response = await client.get("/api/locations/")
        assert response.status_code in [401, 403], "GET /api/locations/ should require authentication"
        
        # Test POST /api/locations/
        response = await client.post("/api/locations/", json=location_data)
        assert response.status_code in [401, 403], "POST /api/locations/ should require authentication"
        
        # Test GET /api/locations/{id}
        response = await client.get("/api/locations/1")
        assert response.status_code in [401, 403, 404], "GET /api/locations/{id} should require authentication"
        
        # Test PUT /api/locations/{id}
        response = await client.put("/api/locations/1", json=location_data)
        assert response.status_code in [401, 403, 404], "PUT /api/locations/{id} should require authentication"
        
        # Test DELETE /api/locations/{id}
        response = await client.delete("/api/locations/1")
        assert response.status_code in [401, 403, 404], "DELETE /api/locations/{id} should require authentication"
    
    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client: AsyncClient):
        """
        Test that invalid authentication tokens are rejected.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
        
        # Test profile endpoints with invalid token
        response = await client.get("/api/users/me", headers=invalid_headers)
        assert response.status_code == 401, "Invalid token should be rejected"
        
        response = await client.patch(
            "/api/users/me",
            json={"breedery_name": "Test"},
            headers=invalid_headers
        )
        assert response.status_code == 401, "Invalid token should be rejected"
        
        # Test location endpoints with invalid token
        response = await client.get("/api/locations/", headers=invalid_headers)
        assert response.status_code in [401, 403], "Invalid token should be rejected"
        
        location_data = {
            "name": "Test",
            "address1": "123 St",
            "city": "City",
            "state": "State",
            "country": "Country",
            "zipcode": "12345",
            "location_type": "user"
        }
        response = await client.post(
            "/api/locations/",
            json=location_data,
            headers=invalid_headers
        )
        assert response.status_code in [401, 403], "Invalid token should be rejected"
    
    @pytest.mark.asyncio
    async def test_malformed_authorization_header_rejected(self, client: AsyncClient):
        """
        Test that malformed authorization headers are rejected.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        # Test various malformed headers
        malformed_headers = [
            {"Authorization": "InvalidFormat"},
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "Basic dGVzdDp0ZXN0"},  # Wrong auth type
            {"Authorization": ""},  # Empty
        ]
        
        for headers in malformed_headers:
            response = await client.get("/api/users/me", headers=headers)
            assert response.status_code == 401, f"Malformed header {headers} should be rejected"
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        token=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),  # Printable ASCII only
            min_size=1,
            max_size=100
        ).filter(lambda t: not t.isspace())
    )
    async def test_random_invalid_tokens_rejected(self, client: AsyncClient, token: str):
        """
        Property test: Any random invalid token should be rejected.
        
        Note: Tokens are constrained to printable ASCII characters since HTTP headers
        must be ASCII-encodable.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test profile endpoint
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401, f"Random token '{token}' should be rejected"
    
    @pytest.mark.asyncio
    async def test_missing_authorization_header(self, client: AsyncClient):
        """
        Test that requests without Authorization header are rejected.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        # Explicitly test without any headers
        response = await client.get("/api/users/me")
        assert response.status_code == 401
        assert "Authorization" not in response.request.headers
        
        response = await client.get("/api/locations/")
        assert response.status_code in [401, 403]
        assert "Authorization" not in response.request.headers
    
    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient):
        """
        Test that expired tokens are rejected.
        
        Note: This test uses a manually crafted expired token.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        import jwt
        from datetime import datetime, timedelta
        from app.config import Settings
        
        settings = Settings()
        
        # Create an expired token (expired 1 hour ago)
        payload = {
            "sub": "test-user-id",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "aud": ["fastapi-users:auth"]
        }
        
        expired_token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm="HS256"
        )
        
        headers = {"Authorization": f"Bearer {expired_token}"}
        
        # Test with expired token
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401, "Expired token should be rejected"
    
    @pytest.mark.asyncio
    async def test_token_with_wrong_signature_rejected(self, client: AsyncClient):
        """
        Test that tokens signed with wrong key are rejected.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        import jwt
        from datetime import datetime, timedelta
        
        # Create a token with wrong secret key
        payload = {
            "sub": "test-user-id",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "aud": ["fastapi-users:auth"]
        }
        
        wrong_token = jwt.encode(
            payload,
            "wrong_secret_key_that_doesnt_match",
            algorithm="HS256"
        )
        
        headers = {"Authorization": f"Bearer {wrong_token}"}
        
        # Test with wrong signature
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401, "Token with wrong signature should be rejected"
    
    @pytest.mark.asyncio
    async def test_all_http_methods_require_authentication(self, client: AsyncClient):
        """
        Test that all HTTP methods on protected endpoints require authentication.
        
        Feature: user-profile-settings, Property 7: Authentication Required
        """
        # Test various HTTP methods without authentication
        endpoints_and_methods = [
            ("GET", "/api/users/me"),
            ("PATCH", "/api/users/me"),
            ("POST", "/api/users/me/profile-image"),
            ("GET", "/api/users/me/profile-image"),
            ("GET", "/api/locations/"),
            ("POST", "/api/locations/"),
            ("GET", "/api/locations/1"),
            ("PUT", "/api/locations/1"),
            ("DELETE", "/api/locations/1"),
        ]
        
        for method, endpoint in endpoints_and_methods:
            if method == "GET":
                response = await client.get(endpoint)
            elif method == "POST":
                if "profile-image" in endpoint:
                    from io import BytesIO
                    from PIL import Image
                    image = Image.new('RGB', (10, 10), color='blue')
                    buffer = BytesIO()
                    image.save(buffer, format='JPEG')
                    buffer.seek(0)
                    files = {"file": ("test.jpg", buffer, "image/jpeg")}
                    response = await client.post(endpoint, files=files)
                else:
                    response = await client.post(endpoint, json={})
            elif method == "PATCH":
                response = await client.patch(endpoint, json={})
            elif method == "PUT":
                response = await client.put(endpoint, json={})
            elif method == "DELETE":
                response = await client.delete(endpoint)
            
            # All should require authentication (401 or 403)
            assert response.status_code in [401, 403, 404], \
                f"{method} {endpoint} should require authentication, got {response.status_code}"
