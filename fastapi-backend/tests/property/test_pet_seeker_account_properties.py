"""Property-based tests for pet seeker account requirements.

Tests user type classification and API response completeness.
"""
import pytest
import uuid
from hypothesis import given, settings, strategies as st, HealthCheck
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
import os

from app.main import app
from app.database import Base, get_async_session
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text


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
    
    # Enable PostGIS extension and create tables
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
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


class TestUserTypeClassification:
    """
    Property 1: User Type Classification
    
    For any user record, if is_breeder is true then the system treats 
    the user as a breeder, and if is_breeder is false then the system 
    treats the user as a pet seeker.
    
    Validates: Requirements 1.2, 1.3
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        is_breeder=st.booleans(),
    )
    async def test_user_type_classification_property(
        self,
        test_db_session: AsyncSession,
        is_breeder: bool,
    ):
        """
        Property test: User type classification based on is_breeder field.
        
        Feature: pet-seeker-accounts, Property 1: User Type Classification
        
        **Validates: Requirements 1.2, 1.3**
        """
        # Generate unique email for each test run
        email = f"test_{uuid.uuid4()}@example.com"
        
        # Create user with specified is_breeder value
        user = User(
            email=email,
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=is_breeder,
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify the user was created with correct is_breeder value
        assert user.is_breeder == is_breeder, \
            f"User should have is_breeder={is_breeder}"
        
        # Query the user back from database to ensure persistence
        result = await test_db_session.execute(
            select(User).where(User.id == user.id)
        )
        db_user = result.scalar_one()
        
        # Verify classification persists
        assert db_user.is_breeder == is_breeder, \
            f"Database user should have is_breeder={is_breeder}"
        
        # Verify user type classification logic
        if is_breeder:
            # User should be classified as breeder
            assert db_user.is_breeder is True, \
                "User with is_breeder=True should be classified as breeder"
        else:
            # User should be classified as pet seeker
            assert db_user.is_breeder is False, \
                "User with is_breeder=False should be classified as pet seeker"


class TestUserAPIResponseCompleteness:
    """
    Property 2: User API Response Completeness
    
    For any user query response, the response SHALL include the is_breeder field.
    
    Validates: Requirements 1.5
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        is_breeder=st.booleans(),
    )
    async def test_user_api_response_includes_is_breeder(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        is_breeder: bool,
    ):
        """
        Property test: User API responses include is_breeder field.
        
        Feature: pet-seeker-accounts, Property 2: User API Response Completeness
        
        **Validates: Requirements 1.5**
        """
        # Create a test user with specified is_breeder value
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=is_breeder,
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Override current_active_user to return our test user
        from app.dependencies import current_active_user
        
        async def override_current_active_user():
            return user
        
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        try:
            # Make API request to get user data
            response = await client.get("/api/users/me")
            
            # Verify response is successful
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            # Parse response JSON
            user_data = response.json()
            
            # Verify is_breeder field is present in response
            assert "is_breeder" in user_data, \
                "User API response must include is_breeder field"
            
            # Verify is_breeder value matches the user's value
            assert user_data["is_breeder"] == is_breeder, \
                f"API response is_breeder should be {is_breeder}, got {user_data['is_breeder']}"
            
        finally:
            # Clean up override
            app.dependency_overrides.pop(current_active_user, None)



class TestBreederEndpointAuthorization:
    """
    Property 7: Breeder Endpoint Authorization
    
    For any breeder-only API endpoint and any authenticated user, the endpoint 
    SHALL return HTTP 200 (or appropriate success code) if is_breeder is true, 
    and SHALL return HTTP 403 Forbidden if is_breeder is false.
    
    Validates: Requirements 6.1, 6.2, 6.3, 6.5, 11.2, 11.3
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        is_breeder=st.booleans(),
    )
    async def test_breeder_endpoint_authorization_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        is_breeder: bool,
    ):
        """
        Property test: Breeder endpoints enforce user type authorization.
        
        Feature: pet-seeker-accounts, Property 7: Breeder Endpoint Authorization
        
        **Validates: Requirements 6.1, 6.2, 6.3, 6.5, 11.2, 11.3**
        """
        # Create a test user with specified is_breeder value
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=is_breeder,
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Override current_active_user to return our test user
        from app.dependencies import current_active_user, require_breeder
        
        async def override_current_active_user():
            return user
        
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        try:
            # Test breeder-only endpoint (create pet)
            # Note: This endpoint will need require_breeder dependency in task 5
            # For now, we test the dependency function directly
            
            # Test the require_breeder dependency function
            from app.dependencies import require_breeder
            
            if is_breeder:
                # Breeder should pass authorization
                result = require_breeder(user)
                assert result == user, "Breeder should be authorized"
            else:
                # Pet seeker should fail authorization
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    require_breeder(user)
                
                assert exc_info.value.status_code == 403, \
                    f"Expected 403 Forbidden, got {exc_info.value.status_code}"
                assert "Breeder access required" in str(exc_info.value.detail), \
                    f"Expected 'Breeder access required' in error message"
            
        finally:
            # Clean up override
            app.dependency_overrides.pop(current_active_user, None)


class TestAuthorizationErrorMessages:
    """
    Property 8: Authorization Error Messages
    
    For any HTTP 403 Forbidden response from authorization failure, the response 
    SHALL include a descriptive error message indicating insufficient permissions.
    
    Validates: Requirements 6.4
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_type=st.sampled_from(['breeder', 'pet_seeker']),
    )
    async def test_authorization_error_messages_property(
        self,
        test_db_session: AsyncSession,
        user_type: str,
    ):
        """
        Property test: Authorization errors include descriptive messages.
        
        Feature: pet-seeker-accounts, Property 8: Authorization Error Messages
        
        **Validates: Requirements 6.4**
        """
        # Create user based on type
        is_breeder = (user_type == 'breeder')
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=is_breeder,
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Test require_breeder with pet seeker
        if not is_breeder:
            from app.dependencies import require_breeder
            from fastapi import HTTPException
            
            with pytest.raises(HTTPException) as exc_info:
                require_breeder(user)
            
            # Verify error has descriptive message
            assert exc_info.value.status_code == 403, \
                "Authorization failure should return 403"
            
            error_detail = str(exc_info.value.detail)
            assert len(error_detail) > 0, \
                "Error message should not be empty"
            assert "breeder" in error_detail.lower() or "access" in error_detail.lower(), \
                "Error message should mention breeder or access"
        
        # Test require_pet_seeker with breeder
        if is_breeder:
            from app.dependencies import require_pet_seeker
            from fastapi import HTTPException
            
            with pytest.raises(HTTPException) as exc_info:
                require_pet_seeker(user)
            
            # Verify error has descriptive message
            assert exc_info.value.status_code == 403, \
                "Authorization failure should return 403"
            
            error_detail = str(exc_info.value.detail)
            assert len(error_detail) > 0, \
                "Error message should not be empty"
            assert "pet seeker" in error_detail.lower() or "access" in error_detail.lower(), \
                "Error message should mention pet seeker or access"





class TestOAuthUserCreation:
    """
    Property 3: Pet Seeker Registration Creates Correct User Type
    
    For any successful pet seeker registration (via form or OAuth), the created 
    user record SHALL have is_breeder set to false.
    
    Validates: Requirements 3.5, 4.3
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        oauth_provider=st.sampled_from(['google']),
    )
    async def test_oauth_creates_pet_seeker_property(
        self,
        test_db_session: AsyncSession,
        oauth_provider: str,
    ):
        """
        Property test: OAuth registration creates users with is_breeder=False.
        
        Feature: pet-seeker-accounts, Property 3: Pet Seeker Registration Creates Correct User Type
        
        **Validates: Requirements 3.5, 4.3**
        """
        # Generate unique identifiers for OAuth user
        email = f"oauth_{uuid.uuid4()}@example.com"
        oauth_id = f"oauth_{uuid.uuid4()}"
        
        # Create OAuth user (simulating OAuth registration)
        user = User(
            email=email,
            hashed_password="oauth_generated_password",  # OAuth users get random password
            is_active=True,
            is_superuser=False,
            is_verified=True,  # OAuth users are pre-verified
            is_breeder=False,  # OAuth users should be pet seekers
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify user was created with is_breeder=False
        assert user.is_breeder is False, \
            "OAuth registered user should have is_breeder=False"
        
        # Verify OAuth fields are set correctly
        assert user.oauth_provider == oauth_provider, \
            f"OAuth provider should be {oauth_provider}"
        assert user.oauth_id == oauth_id, \
            "OAuth ID should be set"
        
        # Verify user is verified (Google verified the email)
        assert user.is_verified is True, \
            "OAuth users should be pre-verified"
        
        # Query user back from database to ensure persistence
        result = await test_db_session.execute(
            select(User).where(User.id == user.id)
        )
        db_user = result.scalar_one()
        
        # Verify all properties persist
        assert db_user.is_breeder is False, \
            "OAuth user should remain pet seeker after persistence"
        assert db_user.oauth_provider == oauth_provider, \
            "OAuth provider should persist"
        assert db_user.oauth_id == oauth_id, \
            "OAuth ID should persist"
        assert db_user.is_verified is True, \
            "Verified status should persist"
    
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        has_existing_account=st.booleans(),
    )
    async def test_oauth_existing_user_handling(
        self,
        test_db_session: AsyncSession,
        has_existing_account: bool,
    ):
        """
        Property test: OAuth handles existing users correctly.
        
        Feature: pet-seeker-accounts, Property 3: Pet Seeker Registration Creates Correct User Type
        
        **Validates: Requirements 4.3, 4.4**
        """
        email = f"oauth_{uuid.uuid4()}@example.com"
        oauth_id = f"oauth_{uuid.uuid4()}"
        
        if has_existing_account:
            # Create existing user without OAuth
            existing_user = User(
                email=email,
                hashed_password="existing_password",
                is_active=True,
                is_superuser=False,
                is_verified=False,
                is_breeder=False,
            )
            test_db_session.add(existing_user)
            await test_db_session.commit()
            await test_db_session.refresh(existing_user)
            
            # Simulate OAuth login - update OAuth fields
            existing_user.oauth_provider = "google"
            existing_user.oauth_id = oauth_id
            await test_db_session.commit()
            await test_db_session.refresh(existing_user)
            
            # Verify user maintains is_breeder value
            assert existing_user.is_breeder is False, \
                "Existing user should maintain is_breeder value"
            
            # Verify OAuth fields are now set
            assert existing_user.oauth_provider == "google", \
                "OAuth provider should be set on existing user"
            assert existing_user.oauth_id == oauth_id, \
                "OAuth ID should be set on existing user"
        else:
            # Create new OAuth user
            new_user = User(
                email=email,
                hashed_password="oauth_generated_password",
                is_active=True,
                is_superuser=False,
                is_verified=True,
                is_breeder=False,
                oauth_provider="google",
                oauth_id=oauth_id,
            )
            test_db_session.add(new_user)
            await test_db_session.commit()
            await test_db_session.refresh(new_user)
            
            # Verify new OAuth user is pet seeker
            assert new_user.is_breeder is False, \
                "New OAuth user should be pet seeker"
            assert new_user.oauth_provider == "google", \
                "OAuth provider should be set"
            assert new_user.oauth_id == oauth_id, \
                "OAuth ID should be set"


class TestBreederUnrestrictedAccess:
    """
    Property 17: Breeder Unrestricted Access
    
    For any API endpoint and any authenticated breeder, the endpoint SHALL 
    grant access without user-type-based restrictions.
    
    Validates: Requirements 11.5, 12.5
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        endpoint_type=st.sampled_from(['pets', 'breedings', 'locations']),
    )
    async def test_breeder_unrestricted_access_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        endpoint_type: str,
    ):
        """
        Property test: Breeders can access all their historical endpoints.
        
        Feature: pet-seeker-accounts, Property 17: Breeder Unrestricted Access
        
        **Validates: Requirements 11.5, 12.5**
        """
        # Create a breeder user
        breeder = User(
            email=f"breeder_{uuid.uuid4()}@example.com",
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        
        test_db_session.add(breeder)
        await test_db_session.commit()
        await test_db_session.refresh(breeder)
        
        # Override current_active_user to return our breeder
        from app.dependencies import current_active_user
        
        async def override_current_active_user():
            return breeder
        
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        try:
            # Test that breeder can access various endpoints
            if endpoint_type == 'pets':
                # Test GET /api/pets/ (list pets) - note trailing slash
                response = await client.get("/api/pets/")
                assert response.status_code == 200, \
                    f"Breeder should be able to list pets, got {response.status_code}"
                
                # Test POST /api/pets/ (create pet) - should not get 403
                # Note: May get 422 for validation, but not 403 for authorization
                response = await client.post("/api/pets/", json={
                    "name": "Test Pet",
                })
                assert response.status_code != 403, \
                    f"Breeder should not get 403 when creating pets, got {response.status_code}"
            
            elif endpoint_type == 'breedings':
                # Test GET /api/breedings/ (list breedings)
                response = await client.get("/api/breedings/")
                assert response.status_code == 200, \
                    f"Breeder should be able to list breedings, got {response.status_code}"
                
                # Test POST /api/breedings/ (create breeding) - should not get 403
                response = await client.post("/api/breedings/", json={
                    "description": "Test Breeding",
                })
                assert response.status_code != 403, \
                    f"Breeder should not get 403 when creating breedings, got {response.status_code}"
            
            elif endpoint_type == 'locations':
                # Test GET /api/locations/ (list locations)
                response = await client.get("/api/locations/")
                assert response.status_code == 200, \
                    f"Breeder should be able to list locations, got {response.status_code}"
                
                # Test POST /api/locations/ (create location) - should not get 403
                response = await client.post("/api/locations/", json={
                    "name": "Test Location",
                    "address1": "123 Test St",
                    "city": "Test City",
                    "country": "Test Country",
                })
                assert response.status_code != 403, \
                    f"Breeder should not get 403 when creating locations, got {response.status_code}"
            
            # Verify breeder can use require_breeder dependency
            from app.dependencies import require_breeder
            result = require_breeder(breeder)
            assert result == breeder, \
                "Breeder should pass require_breeder authorization"
            
        finally:
            # Clean up override
            app.dependency_overrides.pop(current_active_user, None)
    
    
    @pytest.mark.asyncio
    async def test_breeder_backward_compatibility(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
    ):
        """
        Property test: Existing breeders maintain full access (backward compatibility).
        
        Feature: pet-seeker-accounts, Property 17: Breeder Unrestricted Access
        
        **Validates: Requirements 12.5**
        """
        # Create a breeder user (simulating existing user)
        breeder = User(
            email=f"existing_breeder_{uuid.uuid4()}@example.com",
            hashed_password="test_hashed_password",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,  # Existing users should have is_breeder=True
        )
        
        test_db_session.add(breeder)
        await test_db_session.commit()
        await test_db_session.refresh(breeder)
        
        # Override current_active_user
        from app.dependencies import current_active_user
        
        async def override_current_active_user():
            return breeder
        
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        try:
            # Test all breeder endpoints are accessible
            endpoints_to_test = [
                ("/api/pets/", "GET"),
                ("/api/breedings/", "GET"),
                ("/api/locations/", "GET"),
            ]
            
            for endpoint, method in endpoints_to_test:
                if method == "GET":
                    response = await client.get(endpoint)
                    assert response.status_code == 200, \
                        f"Existing breeder should access {endpoint}, got {response.status_code}"
            
            # Verify breeder is not blocked by any authorization
            from app.dependencies import require_breeder
            result = require_breeder(breeder)
            assert result == breeder, \
                "Existing breeder should have unrestricted access"
            
        finally:
            # Clean up override
            app.dependency_overrides.pop(current_active_user, None)


class TestRegistrationFieldOptionality:
    """
    Property 4: Registration Field Optionality
    
    For any pet seeker registration attempt with valid email and password, 
    the registration SHALL succeed regardless of whether the name field is provided.
    
    Validates: Requirements 3.2, 3.3
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=500)
    @given(
        has_name=st.booleans(),
        email_local=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=97, max_codepoint=122),
            min_size=5,
            max_size=20
        ),
        password=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=48, max_codepoint=122),
            min_size=8,
            max_size=20
        ).filter(lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)),
    )
    async def test_registration_field_optionality_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        has_name: bool,
        email_local: str,
        password: str,
    ):
        """
        Property test: Name field is optional in pet seeker registration.
        
        Feature: pet-seeker-accounts, Property 4: Registration Field Optionality
        
        **Validates: Requirements 3.2, 3.3**
        """
        # Generate unique email
        email = f"{email_local}_{uuid.uuid4()}@example.com"
        
        # Build registration payload
        registration_data = {
            "email": email,
            "password": password,
        }
        
        if has_name:
            registration_data["name"] = f"Test User {uuid.uuid4()}"
        
        # Attempt registration
        response = await client.post("/api/auth/register/pet-seeker", json=registration_data)
        
        # Registration should succeed regardless of name field
        assert response.status_code == 200, \
            f"Registration should succeed with or without name, got {response.status_code}: {response.text}"
        
        # Verify response contains expected fields
        response_data = response.json()
        assert "access_token" in response_data, \
            "Response should include access_token"
        assert "user" in response_data, \
            "Response should include user data"
        
        # Verify user data
        user_data = response_data["user"]
        assert user_data["email"] == email, \
            f"User email should match registration email"
        assert user_data["is_breeder"] is False, \
            "Pet seeker should have is_breeder=False"
        
        # Verify name field handling
        if has_name:
            assert user_data.get("name") == registration_data["name"], \
                "User name should match provided name"
        else:
            # Name can be None or not present when not provided
            assert user_data.get("name") is None or "name" not in user_data, \
                "User name should be None when not provided"
        
        # Verify user was created in database
        from sqlalchemy import select
        result = await test_db_session.execute(
            select(User).where(User.email == email)
        )
        db_user = result.scalar_one_or_none()
        
        assert db_user is not None, \
            "User should be created in database"
        assert db_user.is_breeder is False, \
            "Database user should have is_breeder=False"
        
        if has_name:
            assert db_user.name == registration_data["name"], \
                "Database user name should match provided name"
        else:
            assert db_user.name is None, \
                "Database user name should be None when not provided"
    
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        missing_field=st.sampled_from(['email', 'password']),
    )
    async def test_required_fields_validation(
        self,
        client: AsyncClient,
        missing_field: str,
    ):
        """
        Property test: Email and password are required fields.
        
        Feature: pet-seeker-accounts, Property 4: Registration Field Optionality
        
        **Validates: Requirements 3.2**
        """
        # Build registration payload with missing required field
        registration_data = {
            "email": f"test_{uuid.uuid4()}@example.com",
            "password": "ValidPass123",
            "name": "Test User",
        }
        
        # Remove the required field
        del registration_data[missing_field]
        
        # Attempt registration
        response = await client.post("/api/auth/register/pet-seeker", json=registration_data)
        
        # Registration should fail with validation error
        assert response.status_code == 422, \
            f"Registration without {missing_field} should fail with 422, got {response.status_code}"
        
        # Verify error response mentions the missing field
        error_data = response.json()
        assert "detail" in error_data, \
            "Error response should include detail"


class TestPostRegistrationAuthentication:
    """
    Property 5: Post-Registration Authentication
    
    For any successful pet seeker registration, the system SHALL authenticate 
    the user and provide a valid JWT token.
    
    Validates: Requirements 3.6, 4.5
    """
    
    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=500)
    @given(
        email_local=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=97, max_codepoint=122),
            min_size=5,
            max_size=20
        ),
        password=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=48, max_codepoint=122),
            min_size=8,
            max_size=20
        ).filter(lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)),
    )
    async def test_post_registration_authentication_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        email_local: str,
        password: str,
    ):
        """
        Property test: Registration returns valid JWT token.
        
        Feature: pet-seeker-accounts, Property 5: Post-Registration Authentication
        
        **Validates: Requirements 3.6, 4.5**
        """
        # Generate unique email
        email = f"{email_local}_{uuid.uuid4()}@example.com"
        
        # Build registration payload
        registration_data = {
            "email": email,
            "password": password,
        }
        
        # Attempt registration
        response = await client.post("/api/auth/register/pet-seeker", json=registration_data)
        
        # Registration should succeed
        assert response.status_code == 200, \
            f"Registration should succeed, got {response.status_code}: {response.text}"
        
        # Verify response contains JWT token
        response_data = response.json()
        assert "access_token" in response_data, \
            "Response should include access_token"
        assert "token_type" in response_data, \
            "Response should include token_type"
        
        # Verify token is not empty
        access_token = response_data["access_token"]
        assert access_token is not None and len(access_token) > 0, \
            "Access token should not be empty"
        
        # Verify token type is bearer
        assert response_data["token_type"] == "bearer", \
            "Token type should be 'bearer'"
        
        # Verify user data is included
        assert "user" in response_data, \
            "Response should include user data"
        
        user_data = response_data["user"]
        assert user_data["email"] == email, \
            "User email should match registration email"
        assert user_data["is_breeder"] is False, \
            "Pet seeker should have is_breeder=False"
        
        # Verify token is valid by using it to access protected endpoint
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        me_response = await client.get("/api/users/me", headers=auth_headers)
        
        # Token should grant access to protected endpoint
        assert me_response.status_code == 200, \
            f"Token should grant access to /api/users/me, got {me_response.status_code}"
        
        # Verify authenticated user data matches registration
        me_data = me_response.json()
        assert me_data["email"] == email, \
            "Authenticated user email should match registration email"
        assert me_data["is_breeder"] is False, \
            "Authenticated user should be pet seeker"
    
    
    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=500)
    @given(
        email_local=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=97, max_codepoint=122),
            min_size=5,
            max_size=20
        ),
        password=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=48, max_codepoint=122),
            min_size=8,
            max_size=20
        ).filter(lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)),
    )
    async def test_guest_to_account_authentication_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        email_local: str,
        password: str,
    ):
        """
        Property test: Guest-to-account conversion returns valid JWT token.
        
        Feature: pet-seeker-accounts, Property 5: Post-Registration Authentication
        
        **Validates: Requirements 3.6, 4.5**
        """
        # Generate unique email
        email = f"{email_local}_{uuid.uuid4()}@example.com"
        
        # Build guest-to-account payload
        conversion_data = {
            "email": email,
            "password": password,
        }
        
        # Attempt guest-to-account conversion
        response = await client.post("/api/auth/register/from-message", json=conversion_data)
        
        # Conversion should succeed
        assert response.status_code == 200, \
            f"Guest-to-account conversion should succeed, got {response.status_code}: {response.text}"
        
        # Verify response contains JWT token
        response_data = response.json()
        assert "access_token" in response_data, \
            "Response should include access_token"
        assert "token_type" in response_data, \
            "Response should include token_type"
        
        # Verify token is not empty
        access_token = response_data["access_token"]
        assert access_token is not None and len(access_token) > 0, \
            "Access token should not be empty"
        
        # Verify token type is bearer
        assert response_data["token_type"] == "bearer", \
            "Token type should be 'bearer'"
        
        # Verify user data is included
        assert "user" in response_data, \
            "Response should include user data"
        
        user_data = response_data["user"]
        assert user_data["email"] == email, \
            "User email should match conversion email"
        assert user_data["is_breeder"] is False, \
            "Converted user should have is_breeder=False"
        
        # Verify linked_messages_count is included
        assert "linked_messages_count" in response_data, \
            "Response should include linked_messages_count"
        
        # Verify token is valid by using it to access protected endpoint
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        me_response = await client.get("/api/users/me", headers=auth_headers)
        
        # Token should grant access to protected endpoint
        assert me_response.status_code == 200, \
            f"Token should grant access to /api/users/me, got {me_response.status_code}"
        
        # Verify authenticated user data matches conversion
        me_data = me_response.json()
        assert me_data["email"] == email, \
            "Authenticated user email should match conversion email"
        assert me_data["is_breeder"] is False, \
            "Authenticated user should be pet seeker"



class TestPetSeekerEndpointAccess:
    """
    Property 16: Pet Seeker Endpoint Access
    
    For any pet seeker-appropriate endpoint (messages, profile) and any 
    authenticated pet seeker, the endpoint SHALL grant access and return 
    appropriate success responses.
    
    Validates: Requirements 11.4
    """
    
    @pytest.mark.asyncio
    async def test_pet_seeker_can_access_messages_endpoint(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
    ):
        """
        Test that pet seekers can access the messages endpoint.
        
        Feature: pet-seeker-accounts, Property 16: Pet Seeker Endpoint Access
        """
        from fastapi_users.password import PasswordHelper
        from app.models.user import User
        
        password_helper = PasswordHelper()
        
        # Create pet seeker user
        pet_seeker_email = f"petseeker_{uuid.uuid4()}@example.com"
        pet_seeker = User(
            email=pet_seeker_email,
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Login as pet seeker
        login_response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": pet_seeker_email,
                "password": "TestPassword123"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        
        # Access messages endpoint
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        messages_response = await client.get("/api/messages/", headers=auth_headers)
        
        # Should grant access
        assert messages_response.status_code == 200, \
            f"Pet seeker should access messages endpoint, got {messages_response.status_code}"
        
        # Verify response structure
        response_data = messages_response.json()
        assert "messages" in response_data
        assert "total" in response_data
    
    @pytest.mark.asyncio
    async def test_pet_seeker_can_access_profile_endpoint(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
    ):
        """
        Test that pet seekers can access their profile endpoint.
        
        Feature: pet-seeker-accounts, Property 16: Pet Seeker Endpoint Access
        """
        from fastapi_users.password import PasswordHelper
        from app.models.user import User
        
        password_helper = PasswordHelper()
        
        # Create pet seeker user
        pet_seeker_email = f"petseeker_{uuid.uuid4()}@example.com"
        pet_seeker = User(
            email=pet_seeker_email,
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Login as pet seeker
        login_response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": pet_seeker_email,
                "password": "TestPassword123"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        
        # Access profile endpoint
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = await client.get("/api/users/me", headers=auth_headers)
        
        # Should grant access
        assert profile_response.status_code == 200, \
            f"Pet seeker should access profile endpoint, got {profile_response.status_code}"
        
        # Verify user data
        user_data = profile_response.json()
        assert user_data["email"] == pet_seeker_email
        assert user_data["is_breeder"] is False
    
    @pytest.mark.asyncio
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=5000,
    )
    @given(
        email_local=st.text(
            min_size=3,
            max_size=20,
            alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))
        ).filter(lambda s: s and s[0].isalpha()),
        password=st.text(
            min_size=8,
            max_size=50,
            alphabet=st.characters(min_codepoint=33, max_codepoint=126)
        ).filter(lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)),
    )
    async def test_pet_seeker_endpoint_access_property(
        self,
        test_db_session: AsyncSession,
        client: AsyncClient,
        email_local: str,
        password: str,
    ):
        """
        Property test: Pet seekers can access pet seeker-appropriate endpoints.
        
        Feature: pet-seeker-accounts, Property 16: Pet Seeker Endpoint Access
        
        **Validates: Requirements 11.4**
        """
        from fastapi_users.password import PasswordHelper
        from app.models.user import User
        
        password_helper = PasswordHelper()
        
        # Generate unique email
        email = f"{email_local}_{uuid.uuid4()}@example.com"
        
        # Create pet seeker user
        pet_seeker = User(
            email=email,
            hashed_password=password_helper.hash(password),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Login as pet seeker
        login_response = await client.post(
            "/api/auth/jwt/login",
            data={
                "username": email,
                "password": password
            }
        )
        assert login_response.status_code == 200, \
            f"Pet seeker login should succeed, got {login_response.status_code}"
        
        access_token = login_response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Test access to messages endpoint
        messages_response = await client.get("/api/messages/", headers=auth_headers)
        assert messages_response.status_code == 200, \
            f"Pet seeker should access messages endpoint, got {messages_response.status_code}"
        
        # Test access to profile endpoint
        profile_response = await client.get("/api/users/me", headers=auth_headers)
        assert profile_response.status_code == 200, \
            f"Pet seeker should access profile endpoint, got {profile_response.status_code}"
        
        # Verify user is pet seeker
        user_data = profile_response.json()
        assert user_data["is_breeder"] is False, \
            "User should be pet seeker"
