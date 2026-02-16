"""Integration tests for authorization and access control."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.pet import Pet
from app.models.breeding import Breeding
from app.models.location import Location


class TestAuthorizationFlow:
    """Test authorization and access control for different user types."""
    
    @pytest.mark.asyncio
    async def test_pet_seeker_blocked_from_pet_creation(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that pet seekers cannot create pets (403 Forbidden).
        
        Requirements: 6.1, 6.3, 6.4, 6.5
        """
        # Create pet seeker user
        pet_seeker = User(
            email="petseeker@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        # Create authenticated client for pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Attempt to create a pet
            pet_data = {
                "name": "Test Pet",
                "breed_id": 1,
                "sex": "male",
                "date_of_birth": "2024-01-01"
            }
            
            response = await client.post("/api/pets", json=pet_data)
            
            # Should be forbidden
            assert response.status_code == 403
            data = response.json()
            assert "detail" in data
            assert "breeder" in data["detail"].lower() or "permission" in data["detail"].lower()
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_pet_seeker_blocked_from_breeding_creation(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that pet seekers cannot create breedings (403 Forbidden).
        
        Requirements: 6.1, 6.3, 6.5
        """
        # Create pet seeker user
        pet_seeker = User(
            email="petseeker2@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker 2",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        # Create authenticated client for pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Attempt to create a breeding
            breeding_data = {
                "mother_id": "00000000-0000-0000-0000-000000000001",
                "father_id": "00000000-0000-0000-0000-000000000002",
                "breeding_date": "2024-01-01"
            }
            
            response = await client.post("/api/breedings", json=breeding_data)
            
            # Should be forbidden
            assert response.status_code == 403
            data = response.json()
            assert "detail" in data
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_pet_seeker_blocked_from_location_creation(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that pet seekers cannot create locations (403 Forbidden).
        
        Requirements: 6.1, 6.3, 6.5
        """
        # Create pet seeker user
        pet_seeker = User(
            email="petseeker3@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker 3",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        # Create authenticated client for pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Attempt to create a location
            location_data = {
                "address": "123 Test St",
                "city": "Test City",
                "zip": "12345"
            }
            
            response = await client.post("/api/locations", json=location_data)
            
            # Should be forbidden
            assert response.status_code == 403
            data = response.json()
            assert "detail" in data
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_breeder_can_access_all_endpoints(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that breeders can access all breeder endpoints (200 OK).
        
        Requirements: 6.1, 6.5
        """
        # test_user is a breeder by default
        assert test_user.is_breeder is True
        
        # Create authenticated client for breeder
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return test_user
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Test accessing pets list (should succeed)
            response = await client.get("/api/pets")
            assert response.status_code == 200
            
            # Test accessing breedings list (should succeed)
            response = await client.get("/api/breedings")
            assert response.status_code == 200
            
            # Test accessing locations list (should succeed)
            response = await client.get("/api/locations")
            assert response.status_code == 200
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_authorization_error_messages_are_descriptive(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that authorization errors include descriptive messages.
        
        Requirements: 6.4
        """
        # Create pet seeker user
        pet_seeker = User(
            email="petseeker4@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker 4",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        # Create authenticated client for pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Attempt to access breeder endpoint
            response = await client.post("/api/pets", json={
                "name": "Test",
                "breed_id": 1,
                "sex": "male",
                "date_of_birth": "2024-01-01"
            })
            
            assert response.status_code == 403
            data = response.json()
            
            # Verify error message is descriptive
            assert "detail" in data
            assert isinstance(data["detail"], str)
            assert len(data["detail"]) > 0
            # Should mention breeder or permission
            assert any(word in data["detail"].lower() for word in ["breeder", "permission", "access", "forbidden"])
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_pet_seeker_can_access_messages(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that pet seekers can access messages endpoint.
        
        Requirements: 11.4
        """
        # Create pet seeker user
        pet_seeker = User(
            email="petseeker5@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker 5",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        # Create authenticated client for pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Pet seeker should be able to access messages
            response = await client.get("/api/messages/")
            
            # Should succeed (200 OK)
            assert response.status_code == 200
            data = response.json()
            assert "messages" in data
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_complete_authorization_flow(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test complete authorization flow for both user types.
        
        Requirements: 6.1, 6.3, 6.4, 6.5
        """
        # Create pet seeker
        pet_seeker = User(
            email="petseeker6@example.com",
            hashed_password="hashed_password",
            name="Pet Seeker 6",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(pet_seeker)
        await async_session.commit()
        await async_session.refresh(pet_seeker)
        
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        # Test 1: Pet seeker blocked from breeder endpoints
        async def override_get_async_session():
            yield async_session
        
        async def override_pet_seeker():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_pet_seeker
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.post("/api/pets", json={
                "name": "Test",
                "breed_id": 1,
                "sex": "male",
                "date_of_birth": "2024-01-01"
            })
            assert response.status_code == 403
            assert "detail" in response.json()
        
        app.dependency_overrides.clear()
        
        # Test 2: Breeder can access all endpoints
        async def override_breeder():
            return test_user
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_breeder
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            # Breeder can access pets
            response = await client.get("/api/pets")
            assert response.status_code == 200
            
            # Breeder can access breedings
            response = await client.get("/api/breedings")
            assert response.status_code == 200
            
            # Breeder can access locations
            response = await client.get("/api/locations")
            assert response.status_code == 200
        
        app.dependency_overrides.clear()
