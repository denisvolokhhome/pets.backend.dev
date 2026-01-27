"""Integration tests for litters API endpoints.

Tests the complete litter management workflow including:
- Creating litters
- Listing litters
- Getting single litter
- Updating litters
- Deleting litters
- Associating multiple pets with a litter
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.models.litter import Litter
from app.models.pet import Pet
from app.models.user import User


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


class TestLitterCreation:
    """Integration tests for litter creation."""

    @pytest.mark.asyncio
    async def test_create_litter_with_description(self, client: AsyncClient):
        """
        Test creating a litter with description.
        
        Validates: Requirements 4.1, 4.3, 4.4, 4.5
        """
        litter_data = {
            "description": "Test litter with description"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response contains all required fields
        assert "id" in data
        assert data["description"] == litter_data["description"]
        assert data["status"] == "Started"  # Default status
        assert "created_at" in data
        assert "updated_at" in data
        assert data["parent_pets"] is None  # No parent pets yet
        assert data["puppies"] is None  # No puppies yet

    @pytest.mark.asyncio
    async def test_create_litter_without_description(self, client: AsyncClient):
        """
        Test creating a litter without description (minimal fields).
        
        Validates: Requirements 4.1, 4.3, 4.4, 4.5
        """
        litter_data = {}
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert "id" in data
        assert data["description"] is None
        assert data["status"] == "Started"  # Default status
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_litter_default_status_is_started(self, client: AsyncClient):
        """
        Test that newly created litters have status "Started" by default.
        
        Validates: Requirements 2.1, 4.3
        """
        litter_data = {
            "description": "Testing default status"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "Started", "New litter should have status 'Started'"

    @pytest.mark.asyncio
    async def test_create_litter_timestamps_are_set(self, client: AsyncClient):
        """
        Test that created_at and updated_at timestamps are set on creation.
        
        Validates: Requirements 4.4, 4.5
        """
        litter_data = {
            "description": "Testing timestamps"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify timestamps exist and are valid
        assert "created_at" in data
        assert "updated_at" in data
        assert data["created_at"] is not None
        
        # Parse timestamps to verify they're valid datetime strings
        from datetime import datetime
        created_at = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
        assert created_at is not None
        
        # Verify created_at is recent (within last minute)
        now = datetime.now(created_at.tzinfo)
        time_diff = (now - created_at).total_seconds()
        assert time_diff < 60, "created_at should be recent"

    @pytest.mark.asyncio
    async def test_create_multiple_litters(self, client: AsyncClient):
        """
        Test creating multiple litters.
        
        Validates: Requirements 4.1
        """
        litters_data = [
            {"description": "First litter"},
            {"description": "Second litter"},
            {"description": None}  # No description
        ]
        
        created_ids = []
        for litter_data in litters_data:
            response = await client.post("/api/litters/", json=litter_data)
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "Started"
            created_ids.append(data["id"])
        
        # Verify all litters have unique IDs
        assert len(created_ids) == len(set(created_ids)), "All litters should have unique IDs"


class TestLitterListing:
    """Integration tests for listing litters."""

    @pytest.mark.asyncio
    async def test_list_litters_empty(self, client: AsyncClient):
        """
        Test listing litters when database is empty.
        
        Validates: Requirements 7.1, 13.4
        """
        response = await client.get("/api/litters/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_litters_with_data(self, client: AsyncClient):
        """
        Test listing litters with multiple litters in database.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create multiple litters
        litters_data = [
            {"description": "Litter 1"},
            {"description": "Litter 2"},
            {"description": "Litter 3"}
        ]
        
        created_ids = []
        for litter_data in litters_data:
            response = await client.post("/api/litters/", json=litter_data)
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
        
        # List all litters
        response = await client.get("/api/litters/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= len(litters_data)
        
        # Verify our created litters are in the list
        litter_ids = [l["id"] for l in data]
        for litter_id in created_ids:
            assert litter_id in litter_ids

    @pytest.mark.asyncio
    async def test_list_litters_without_filters(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test listing litters without any filters returns all non-voided litters.
        
        Validates: Requirements 10.1, 10.2, 10.3
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create litters with different statuses
        litter1 = Litter(
            date_of_litter=date.today(),
            description="Started litter",
            status="Started"
        )
        litter2 = Litter(
            date_of_litter=date.today(),
            description="InProcess litter",
            status="InProcess"
        )
        litter3 = Litter(
            date_of_litter=date.today(),
            description="Done litter",
            status="Done"
        )
        litter4 = Litter(
            date_of_litter=date.today(),
            description="Voided litter",
            status="Voided"
        )
        
        async_session.add_all([litter1, litter2, litter3, litter4])
        await async_session.commit()
        
        for litter in [litter1, litter2, litter3, litter4]:
            await async_session.refresh(litter)
        
        # List litters without filters
        response = await client.get("/api/litters/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify voided litter is excluded by default
        litter_ids = [l["id"] for l in data]
        assert litter1.id in litter_ids
        assert litter2.id in litter_ids
        assert litter3.id in litter_ids
        assert litter4.id not in litter_ids  # Voided should be excluded

    @pytest.mark.asyncio
    async def test_list_litters_filter_by_location(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test filtering litters by location.
        
        Validates: Requirements 10.1
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create two locations
        location1 = Location(
            user_id=test_user.id,
            name="Location 1",
            address1="123 Main St",
            city="City1",
            state="State1",
            country="Country1",
            zipcode="12345",
            location_type="pet"
        )
        location2 = Location(
            user_id=test_user.id,
            name="Location 2",
            address1="456 Oak Ave",
            city="City2",
            state="State2",
            country="Country2",
            zipcode="67890",
            location_type="pet"
        )
        async_session.add_all([location1, location2])
        await async_session.commit()
        await async_session.refresh(location1)
        await async_session.refresh(location2)
        
        # Create litters
        litter1 = Litter(
            date_of_litter=date.today(),
            description="Litter at location 1",
            status="InProcess"
        )
        litter2 = Litter(
            date_of_litter=date.today(),
            description="Litter at location 2",
            status="InProcess"
        )
        async_session.add_all([litter1, litter2])
        await async_session.commit()
        await async_session.refresh(litter1)
        await async_session.refresh(litter2)
        
        # Create parent pets for litter1 at location1
        pet1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location1.id,
            is_puppy=False
        )
        pet2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location1.id,
            is_puppy=False
        )
        async_session.add_all([pet1, pet2])
        await async_session.commit()
        await async_session.refresh(pet1)
        await async_session.refresh(pet2)
        
        # Assign pets to litter1
        litter_pet1 = LitterPet(litter_id=litter1.id, pet_id=pet1.id)
        litter_pet2 = LitterPet(litter_id=litter1.id, pet_id=pet2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Create parent pets for litter2 at location2
        pet3 = Pet(
            user_id=test_user.id,
            name="Parent 3",
            location_id=location2.id,
            is_puppy=False
        )
        pet4 = Pet(
            user_id=test_user.id,
            name="Parent 4",
            location_id=location2.id,
            is_puppy=False
        )
        async_session.add_all([pet3, pet4])
        await async_session.commit()
        await async_session.refresh(pet3)
        await async_session.refresh(pet4)
        
        # Assign pets to litter2
        litter_pet3 = LitterPet(litter_id=litter2.id, pet_id=pet3.id)
        litter_pet4 = LitterPet(litter_id=litter2.id, pet_id=pet4.id)
        async_session.add_all([litter_pet3, litter_pet4])
        await async_session.commit()
        
        # Filter by location1
        response = await client.get(f"/api/litters/?location_id={location1.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify only litter1 is returned
        litter_ids = [l["id"] for l in data]
        assert litter1.id in litter_ids
        assert litter2.id not in litter_ids

    @pytest.mark.asyncio
    async def test_list_litters_filter_by_status(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test filtering litters by status.
        
        Validates: Requirements 10.2
        """
        # Create litters with different statuses
        litter1 = Litter(
            date_of_litter=date.today(),
            description="Started litter",
            status="Started"
        )
        litter2 = Litter(
            date_of_litter=date.today(),
            description="InProcess litter",
            status="InProcess"
        )
        litter3 = Litter(
            date_of_litter=date.today(),
            description="Done litter",
            status="Done"
        )
        
        async_session.add_all([litter1, litter2, litter3])
        await async_session.commit()
        
        for litter in [litter1, litter2, litter3]:
            await async_session.refresh(litter)
        
        # Filter by InProcess status
        response = await client.get("/api/litters/?status=InProcess")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify only InProcess litter is returned
        litter_ids = [l["id"] for l in data]
        assert litter2.id in litter_ids
        assert litter1.id not in litter_ids
        assert litter3.id not in litter_ids
        
        # Verify all returned litters have InProcess status
        for litter in data:
            assert litter["status"] == "InProcess"

    @pytest.mark.asyncio
    async def test_list_litters_filter_by_breed(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test filtering litters by breed.
        
        Validates: Requirements 10.3
        """
        from app.models.litter_pet import LitterPet
        from app.models.breed import Breed
        
        # Create two breeds
        breed1 = Breed(name="Breed 1", code="B1")
        breed2 = Breed(name="Breed 2", code="B2")
        async_session.add_all([breed1, breed2])
        await async_session.commit()
        await async_session.refresh(breed1)
        await async_session.refresh(breed2)
        
        # Create litters
        litter1 = Litter(
            date_of_litter=date.today(),
            description="Litter with breed 1",
            status="InProcess"
        )
        litter2 = Litter(
            date_of_litter=date.today(),
            description="Litter with breed 2",
            status="InProcess"
        )
        async_session.add_all([litter1, litter2])
        await async_session.commit()
        await async_session.refresh(litter1)
        await async_session.refresh(litter2)
        
        # Create parent pets for litter1 with breed1
        pet1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            breed_id=breed1.id,
            is_puppy=False
        )
        pet2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            breed_id=breed1.id,
            is_puppy=False
        )
        async_session.add_all([pet1, pet2])
        await async_session.commit()
        await async_session.refresh(pet1)
        await async_session.refresh(pet2)
        
        # Assign pets to litter1
        litter_pet1 = LitterPet(litter_id=litter1.id, pet_id=pet1.id)
        litter_pet2 = LitterPet(litter_id=litter1.id, pet_id=pet2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Create parent pets for litter2 with breed2
        pet3 = Pet(
            user_id=test_user.id,
            name="Parent 3",
            breed_id=breed2.id,
            is_puppy=False
        )
        pet4 = Pet(
            user_id=test_user.id,
            name="Parent 4",
            breed_id=breed2.id,
            is_puppy=False
        )
        async_session.add_all([pet3, pet4])
        await async_session.commit()
        await async_session.refresh(pet3)
        await async_session.refresh(pet4)
        
        # Assign pets to litter2
        litter_pet3 = LitterPet(litter_id=litter2.id, pet_id=pet3.id)
        litter_pet4 = LitterPet(litter_id=litter2.id, pet_id=pet4.id)
        async_session.add_all([litter_pet3, litter_pet4])
        await async_session.commit()
        
        # Filter by breed1
        response = await client.get(f"/api/litters/?breed_id={breed1.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify only litter1 is returned
        litter_ids = [l["id"] for l in data]
        assert litter1.id in litter_ids
        assert litter2.id not in litter_ids

    @pytest.mark.asyncio
    async def test_list_litters_combined_filters(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test filtering litters with multiple filter criteria combined.
        
        Validates: Requirements 10.1, 10.2, 10.3
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create test data
        location1 = Location(
            user_id=test_user.id,
            name="Location 1",
            address1="123 Main St",
            city="City1",
            state="State1",
            country="Country1",
            zipcode="12345",
            location_type="pet"
        )
        location2 = Location(
            user_id=test_user.id,
            name="Location 2",
            address1="456 Oak Ave",
            city="City2",
            state="State2",
            country="Country2",
            zipcode="67890",
            location_type="pet"
        )
        async_session.add_all([location1, location2])
        await async_session.commit()
        await async_session.refresh(location1)
        await async_session.refresh(location2)
        
        breed1 = Breed(name="Breed 1", code="B1")
        breed2 = Breed(name="Breed 2", code="B2")
        async_session.add_all([breed1, breed2])
        await async_session.commit()
        await async_session.refresh(breed1)
        await async_session.refresh(breed2)
        
        # Create litters with different combinations
        # Litter 1: Location1, Breed1, InProcess
        litter1 = Litter(
            date_of_litter=date.today(),
            description="L1-B1-InProcess",
            status="InProcess"
        )
        # Litter 2: Location1, Breed1, Done
        litter2 = Litter(
            date_of_litter=date.today(),
            description="L1-B1-Done",
            status="Done"
        )
        # Litter 3: Location2, Breed2, InProcess
        litter3 = Litter(
            date_of_litter=date.today(),
            description="L2-B2-InProcess",
            status="InProcess"
        )
        
        async_session.add_all([litter1, litter2, litter3])
        await async_session.commit()
        
        for litter in [litter1, litter2, litter3]:
            await async_session.refresh(litter)
        
        # Create and assign pets for litter1
        pet1_1 = Pet(user_id=test_user.id, name="P1_1", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
        pet1_2 = Pet(user_id=test_user.id, name="P1_2", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
        async_session.add_all([pet1_1, pet1_2])
        await async_session.commit()
        await async_session.refresh(pet1_1)
        await async_session.refresh(pet1_2)
        
        lp1_1 = LitterPet(litter_id=litter1.id, pet_id=pet1_1.id)
        lp1_2 = LitterPet(litter_id=litter1.id, pet_id=pet1_2.id)
        async_session.add_all([lp1_1, lp1_2])
        await async_session.commit()
        
        # Create and assign pets for litter2
        pet2_1 = Pet(user_id=test_user.id, name="P2_1", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
        pet2_2 = Pet(user_id=test_user.id, name="P2_2", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
        async_session.add_all([pet2_1, pet2_2])
        await async_session.commit()
        await async_session.refresh(pet2_1)
        await async_session.refresh(pet2_2)
        
        lp2_1 = LitterPet(litter_id=litter2.id, pet_id=pet2_1.id)
        lp2_2 = LitterPet(litter_id=litter2.id, pet_id=pet2_2.id)
        async_session.add_all([lp2_1, lp2_2])
        await async_session.commit()
        
        # Create and assign pets for litter3
        pet3_1 = Pet(user_id=test_user.id, name="P3_1", location_id=location2.id, breed_id=breed2.id, is_puppy=False)
        pet3_2 = Pet(user_id=test_user.id, name="P3_2", location_id=location2.id, breed_id=breed2.id, is_puppy=False)
        async_session.add_all([pet3_1, pet3_2])
        await async_session.commit()
        await async_session.refresh(pet3_1)
        await async_session.refresh(pet3_2)
        
        lp3_1 = LitterPet(litter_id=litter3.id, pet_id=pet3_1.id)
        lp3_2 = LitterPet(litter_id=litter3.id, pet_id=pet3_2.id)
        async_session.add_all([lp3_1, lp3_2])
        await async_session.commit()
        
        # Filter by location1 + breed1 + InProcess
        response = await client.get(
            f"/api/litters/?location_id={location1.id}&breed_id={breed1.id}&status=InProcess"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify only litter1 matches all criteria
        litter_ids = [l["id"] for l in data]
        assert litter1.id in litter_ids
        assert litter2.id not in litter_ids  # Wrong status
        assert litter3.id not in litter_ids  # Wrong location and breed

    @pytest.mark.asyncio
    async def test_list_litters_chronological_order(self, client: AsyncClient):
        """
        Test that litters are returned in chronological order (most recent first).
        
        Validates: Requirements 7.1, 13.4
        """
        # Create litters with different descriptions
        litters_data = [
            {"description": "Oldest"},
            {"description": "Newest"},
            {"description": "Middle"}
        ]
        
        created_litters = []
        for litter_data in litters_data:
            response = await client.post("/api/litters/", json=litter_data)
            assert response.status_code == 201
            created_litters.append(response.json())
        
        # List litters
        response = await client.get("/api/litters/")
        assert response.status_code == 200
        data = response.json()
        
        # Find our test litters in the response
        test_litters = [l for l in data if l["id"] in [cl["id"] for cl in created_litters]]
        
        # Verify they're in descending chronological order (newest first)
        assert len(test_litters) == 3
        dates = [l["date_of_litter"] for l in test_litters]
        assert dates == sorted(dates, reverse=True)

    @pytest.mark.asyncio
    async def test_list_litters_active_only_filter(self, client: AsyncClient):
        """
        Test filtering litters to show only active ones.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create active and inactive litters (note: is_active is no longer used in new spec)
        active_litter = {
            "description": "Active litter"
        }
        inactive_litter = {
            "description": "Inactive litter"
        }
        
        active_response = await client.post("/api/litters/", json=active_litter)
        assert active_response.status_code == 201
        active_id = active_response.json()["id"]
        
        inactive_response = await client.post("/api/litters/", json=inactive_litter)
        assert inactive_response.status_code == 201
        inactive_id = inactive_response.json()["id"]
        
        # List only active litters
        response = await client.get("/api/litters/?active_only=true")
        assert response.status_code == 200
        data = response.json()
        
        # Verify only active litters are returned
        litter_ids = [l["id"] for l in data]
        assert active_id in litter_ids
        assert inactive_id not in litter_ids

    @pytest.mark.asyncio
    async def test_list_litters_pagination(self, client: AsyncClient):
        """
        Test litter listing with pagination parameters.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create several litters
        for i in range(5):
            litter_data = {
                "description": f"Pagination Test Litter {i}"
            }
            await client.post("/api/litters/", json=litter_data)
        
        # Test with limit
        response = await client.get("/api/litters/?limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 3
        
        # Test with skip
        response = await client.get("/api/litters/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2


class TestLitterRetrieval:
    """Integration tests for retrieving single litter."""

    @pytest.mark.asyncio
    async def test_get_litter_by_id_successful_retrieval(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test successful retrieval of a litter by ID with full details.
        
        Validates: Requirements 7.2, 7.3, 7.4
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create a litter
        litter = Litter(
            description="Test litter for retrieval",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Refresh litter to load relationships
        await async_session.refresh(litter)
        
        # Create puppies
        puppy1 = Pet(
            user_id=test_user.id,
            name="Puppy 1",
            litter_id=litter.id,
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            date_of_birth=date.today(),
            microchip="123456789",
            is_puppy=True
        )
        puppy2 = Pet(
            user_id=test_user.id,
            name="Puppy 2",
            litter_id=litter.id,
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            date_of_birth=date.today(),
            microchip="987654321",
            is_puppy=True
        )
        async_session.add_all([puppy1, puppy2])
        await async_session.commit()
        
        # Get the litter
        response = await client.get(f"/api/litters/{litter.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic litter fields
        assert data["id"] == litter.id
        assert data["description"] == "Test litter for retrieval"
        assert data["status"] == "InProcess"
        assert "created_at" in data
        assert "updated_at" in data
        
        # Verify parent_pets are included
        assert data["parent_pets"] is not None
        assert len(data["parent_pets"]) == 2
        parent_names = [p["name"] for p in data["parent_pets"]]
        assert "Parent 1" in parent_names
        assert "Parent 2" in parent_names
        
        # Verify parent pet details
        for parent in data["parent_pets"]:
            assert "id" in parent
            assert "name" in parent
            assert "breed" in parent
            assert parent["breed"] == "Test Breed"
            assert "location" in parent
            assert parent["location"] == "Test Location"
            assert "gender" in parent
        
        # Verify puppies are included
        assert data["puppies"] is not None
        assert len(data["puppies"]) == 2
        puppy_names = [p["name"] for p in data["puppies"]]
        assert "Puppy 1" in puppy_names
        assert "Puppy 2" in puppy_names
        
        # Verify puppy details
        for puppy in data["puppies"]:
            assert "id" in puppy
            assert "name" in puppy
            assert "gender" in puppy
            assert "birth_date" in puppy
            assert "microchip" in puppy

    @pytest.mark.asyncio
    async def test_get_litter_by_id_not_found(self, client: AsyncClient):
        """
        Test that getting a non-existent litter returns 404.
        
        Validates: Requirements 7.2
        """
        # Use a very high ID that shouldn't exist
        response = await client.get("/api/litters/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Litter not found"

    @pytest.mark.asyncio
    async def test_get_litter_with_no_parent_pets(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test retrieving a litter with no parent pets assigned.
        
        Validates: Requirements 7.3, 7.5
        """
        # Create a litter without parent pets
        litter = Litter(
            description="Litter with no parents",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Get the litter
        response = await client.get(f"/api/litters/{litter.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter.id
        assert data["description"] == "Litter with no parents"
        assert data["status"] == "Started"
        assert data["parent_pets"] is None  # No parent pets
        assert data["puppies"] is None  # No puppies

    @pytest.mark.asyncio
    async def test_get_litter_with_no_puppies(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test retrieving a litter with parent pets but no puppies.
        
        Validates: Requirements 7.3, 7.4
        """
        from app.models.litter_pet import LitterPet
        
        # Create a litter
        litter = Litter(
            description="Litter with parents but no puppies",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent A",
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent B",
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Refresh litter to load relationships
        await async_session.refresh(litter)
        
        # Get the litter
        response = await client.get(f"/api/litters/{litter.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter.id
        assert data["status"] == "InProcess"
        
        # Verify parent_pets are included
        assert data["parent_pets"] is not None
        assert len(data["parent_pets"]) == 2
        
        # Verify no puppies
        assert data["puppies"] is None

    @pytest.mark.asyncio
    async def test_get_litter_by_id(self, client: AsyncClient):
        """
        Test getting a single litter by ID.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "description": "Test litter for retrieval"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        created_litter = create_response.json()
        litter_id = created_litter["id"]
        
        # Get the litter
        response = await client.get(f"/api/litters/{litter_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter_id
        assert data["description"] == litter_data["description"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_litter_returns_404(self, client: AsyncClient):
        """
        Test that getting a non-existent litter returns 404.
        
        Validates: Requirements 7.1, 13.4
        """
        # Use a very high ID that shouldn't exist
        response = await client.get("/api/litters/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestLitterUpdate:
    """Integration tests for updating litters."""

    @pytest.mark.asyncio
    async def test_update_litter_successful(self, client: AsyncClient):
        """
        Test successful update of a litter's description.
        
        Validates: Requirements 8.1, 8.2
        """
        # Create a litter
        litter_data = {
            "description": "Original description"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        created_litter = create_response.json()
        litter_id = created_litter["id"]
        original_created_at = created_litter["created_at"]
        
        # Update the litter
        update_data = {
            "description": "Updated description"
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure matches LitterResponse
        assert data["id"] == litter_id
        assert data["description"] == update_data["description"]
        assert data["status"] == "Started"  # Status should remain unchanged
        assert "created_at" in data
        assert "updated_at" in data
        assert data["created_at"] == original_created_at  # created_at should not change
        assert "parent_pets" in data
        assert "puppies" in data

    @pytest.mark.asyncio
    async def test_update_litter_updated_at_changes(self, client: AsyncClient):
        """
        Test that updated_at timestamp changes when litter is updated.
        
        Validates: Requirements 8.2, 8.5
        """
        import asyncio
        from datetime import datetime
        
        # Create a litter
        litter_data = {
            "description": "Test timestamp update"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        created_litter = create_response.json()
        litter_id = created_litter["id"]
        original_updated_at = created_litter["updated_at"]
        
        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(0.1)
        
        # Update the litter
        update_data = {
            "description": "Updated to test timestamp"
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify updated_at has changed
        assert "updated_at" in data
        new_updated_at = data["updated_at"]
        
        # Parse timestamps to compare
        if original_updated_at and new_updated_at:
            original_dt = datetime.fromisoformat(original_updated_at.replace('Z', '+00:00'))
            new_dt = datetime.fromisoformat(new_updated_at.replace('Z', '+00:00'))
            assert new_dt >= original_dt, "updated_at should be equal or later after update"

    @pytest.mark.asyncio
    async def test_update_litter_not_found(self, client: AsyncClient):
        """
        Test that updating a non-existent litter returns 404.
        
        Validates: Requirements 8.2, 8.5
        """
        update_data = {"description": "Updated description"}
        
        response = await client.put("/api/litters/999999", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Litter not found"

    @pytest.mark.asyncio
    async def test_update_litter_with_parent_pets(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test updating a litter that has parent pets assigned.
        
        Validates: Requirements 8.1, 8.2
        """
        from app.models.litter_pet import LitterPet
        
        # Create a litter
        litter = Litter(
            description="Litter with parents",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Update the litter
        update_data = {
            "description": "Updated litter with parents"
        }
        
        response = await client.put(f"/api/litters/{litter.id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify update was successful
        assert data["id"] == litter.id
        assert data["description"] == update_data["description"]
        assert data["status"] == "InProcess"
        
        # Verify parent_pets are still included in response
        assert data["parent_pets"] is not None
        assert len(data["parent_pets"]) == 2
        parent_names = [p["name"] for p in data["parent_pets"]]
        assert "Parent 1" in parent_names
        assert "Parent 2" in parent_names

    @pytest.mark.asyncio
    async def test_update_litter_with_puppies(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test updating a litter that has puppies.
        
        Validates: Requirements 8.1, 8.2
        """
        # Create a litter
        litter = Litter(
            description="Litter with puppies",
            status="Done"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create puppies
        puppy1 = Pet(
            user_id=test_user.id,
            name="Puppy 1",
            litter_id=litter.id,
            gender="Male",
            date_of_birth=date.today(),
            is_puppy=True
        )
        puppy2 = Pet(
            user_id=test_user.id,
            name="Puppy 2",
            litter_id=litter.id,
            gender="Female",
            date_of_birth=date.today(),
            is_puppy=True
        )
        async_session.add_all([puppy1, puppy2])
        await async_session.commit()
        
        # Update the litter
        update_data = {
            "description": "Updated litter with puppies"
        }
        
        response = await client.put(f"/api/litters/{litter.id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify update was successful
        assert data["id"] == litter.id
        assert data["description"] == update_data["description"]
        assert data["status"] == "Done"
        
        # Verify puppies are still included in response
        assert data["puppies"] is not None
        assert len(data["puppies"]) == 2
        puppy_names = [p["name"] for p in data["puppies"]]
        assert "Puppy 1" in puppy_names
        assert "Puppy 2" in puppy_names

    @pytest.mark.asyncio
    async def test_update_litter_empty_description(self, client: AsyncClient):
        """
        Test updating a litter with empty/null description.
        
        Validates: Requirements 8.1, 8.2
        """
        # Create a litter
        litter_data = {
            "description": "Original description"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        litter_id = create_response.json()["id"]
        
        # Update with null description
        update_data = {
            "description": None
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter_id
        assert data["description"] is None

    @pytest.mark.asyncio
    async def test_update_litter_all_fields(self, client: AsyncClient):
        """
        Test updating all fields of a litter.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "description": "Original description"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        litter_id = create_response.json()["id"]
        
        # Update the litter
        update_data = {
            "description": "Updated description"
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter_id
        assert data["description"] == update_data["description"]

    @pytest.mark.asyncio
    async def test_update_litter_partial_fields(self, client: AsyncClient):
        """
        Test updating only some fields of a litter.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "description": "Partial update test"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        created_litter = create_response.json()
        litter_id = created_litter["id"]
        
        # Update only the description
        update_data = {
            "description": "Updated description only"
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter_id
        assert data["description"] == update_data["description"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_litter_returns_404(self, client: AsyncClient):
        """
        Test that updating a non-existent litter returns 404.
        
        Validates: Requirements 7.1, 13.4
        """
        update_data = {"description": "Updated description"}
        
        response = await client.put("/api/litters/999999", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestLitterDeletion:
    """Integration tests for deleting litters."""

    @pytest.mark.asyncio
    async def test_void_litter_successful(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test successfully voiding a litter (soft delete).
        
        Validates: Requirements 9.1, 9.2, 9.3, 9.4
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create a litter with parent pets and puppies
        litter = Litter(
            description="Litter to void",
            status="Done"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Create puppies
        puppy1 = Pet(
            user_id=test_user.id,
            name="Puppy 1",
            litter_id=litter.id,
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            date_of_birth=date.today(),
            microchip="123456789",
            is_puppy=True
        )
        async_session.add(puppy1)
        await async_session.commit()
        
        # Store original updated_at
        original_updated_at = litter.updated_at
        
        # Void the litter
        response = await client.delete(f"/api/litters/{litter.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contains all required fields
        assert data["id"] == litter.id
        assert data["description"] == "Litter to void"
        assert data["status"] == "Voided"  # Status changed to Voided
        assert "created_at" in data
        assert "updated_at" in data
        
        # Verify updated_at was changed
        from datetime import datetime
        updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))
        if original_updated_at:
            original_dt = datetime.fromisoformat(original_updated_at.isoformat().replace('Z', '+00:00'))
            assert updated_at > original_dt, "updated_at should be updated"
        
        # Verify parent pets and puppies are still in response
        assert data["parent_pets"] is not None
        assert len(data["parent_pets"]) == 2
        assert data["puppies"] is not None
        assert len(data["puppies"]) == 1

    @pytest.mark.asyncio
    async def test_void_litter_status_change_to_voided(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that voiding a litter changes status to "Voided".
        
        Validates: Requirements 9.2
        """
        # Create a litter
        litter = Litter(
            description="Test status change",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Void the litter
        response = await client.delete(f"/api/litters/{litter.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify status is Voided
        assert data["status"] == "Voided"
        
        # Verify litter can still be retrieved by ID
        get_response = await client.get(f"/api/litters/{litter.id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["status"] == "Voided"

    @pytest.mark.asyncio
    async def test_void_litter_record_is_maintained(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that voiding a litter maintains the record (soft delete).
        
        Validates: Requirements 9.3, 9.4
        """
        # Create a litter
        litter = Litter(
            description="Test record maintenance",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        litter_id = litter.id
        original_description = litter.description
        
        # Void the litter
        response = await client.delete(f"/api/litters/{litter_id}")
        assert response.status_code == 200
        
        # Verify litter still exists in database
        from sqlalchemy import select
        query = select(Litter).where(Litter.id == litter_id)
        result = await async_session.execute(query)
        db_litter = result.scalar_one_or_none()
        
        assert db_litter is not None, "Litter record should be maintained"
        assert db_litter.description == original_description
        assert db_litter.status == "Voided"
        
        # Verify litter can still be retrieved via API
        get_response = await client.get(f"/api/litters/{litter_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["id"] == litter_id
        assert get_data["description"] == original_description

    @pytest.mark.asyncio
    async def test_void_litter_excluded_from_default_listing(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that voided litters are excluded from default listings.
        
        Validates: Requirements 9.3, 10.1
        """
        # Create active and voided litters
        active_litter = Litter(
            description="Active litter",
            status="Started"
        )
        voided_litter = Litter(
            description="Voided litter",
            status="Started"
        )
        async_session.add_all([active_litter, voided_litter])
        await async_session.commit()
        await async_session.refresh(active_litter)
        await async_session.refresh(voided_litter)
        
        # Void one litter
        await client.delete(f"/api/litters/{voided_litter.id}")
        
        # List litters without filters (should exclude voided)
        response = await client.get("/api/litters/")
        assert response.status_code == 200
        data = response.json()
        
        litter_ids = [l["id"] for l in data]
        assert active_litter.id in litter_ids
        assert voided_litter.id not in litter_ids, "Voided litter should be excluded from default listing"

    @pytest.mark.asyncio
    async def test_void_nonexistent_litter_returns_404(self, client: AsyncClient):
        """
        Test that voiding a non-existent litter returns 404.
        
        Validates: Requirements 9.4
        """
        response = await client.delete("/api/litters/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


class TestLitterPetAssociation:
    """Integration tests for associating pets with litters."""

    @pytest.mark.asyncio
    async def test_associate_multiple_pets_with_litter(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test associating multiple pets with a single litter.
        
        Validates: Requirements 7.1, 7.3, 13.4
        """
        # Create a litter
        litter_data = {
            "description": "Litter with multiple pets"
        }
        
        litter_response = await client.post("/api/litters/", json=litter_data)
        assert litter_response.status_code == 201
        litter_id = litter_response.json()["id"]
        
        # Create multiple pets associated with this litter
        pet_names = ["Puppy 1", "Puppy 2", "Puppy 3"]
        created_pet_ids = []
        
        for name in pet_names:
            pet = Pet(
                user_id=test_user.id,
                name=name,
                litter_id=litter_id
            )
            async_session.add(pet)
        
        await async_session.commit()
        
        # Query pets for this litter
        from sqlalchemy import select
        query = select(Pet).where(Pet.litter_id == litter_id)
        result = await async_session.execute(query)
        litter_pets = result.scalars().all()
        
        # Verify all pets are associated with the litter
        assert len(litter_pets) == len(pet_names)
        
        for pet in litter_pets:
            assert pet.litter_id == litter_id
            assert pet.name in pet_names

    @pytest.mark.asyncio
    async def test_litter_with_no_pets(self, client: AsyncClient):
        """
        Test that a litter can exist without any associated pets.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "description": "Litter with no pets"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        assert response.status_code == 201
        
        # Verify litter was created successfully
        litter_id = response.json()["id"]
        get_response = await client.get(f"/api/litters/{litter_id}")
        assert get_response.status_code == 200


class TestLitterManagementWorkflow:
    """Integration tests for complete litter management workflow."""

    @pytest.mark.asyncio
    async def test_complete_litter_lifecycle(self, client: AsyncClient):
        """
        Test complete litter management workflow: create, read, update, delete.
        
        Validates: Requirements 7.1, 13.4
        """
        # Step 1: Create a litter
        create_data = {
            "description": "Lifecycle test litter"
        }
        
        create_response = await client.post("/api/litters/", json=create_data)
        assert create_response.status_code == 201
        created_litter = create_response.json()
        litter_id = created_litter["id"]
        
        assert created_litter["date_of_litter"] == create_data["date_of_litter"]
        assert created_litter["description"] == create_data["description"]
        assert created_litter["is_active"] == create_data["is_active"]
        
        # Step 2: Read the litter
        get_response = await client.get(f"/api/litters/{litter_id}")
        assert get_response.status_code == 200
        retrieved_litter = get_response.json()
        
        assert retrieved_litter["id"] == litter_id
        assert retrieved_litter["description"] == create_data["description"]
        
        # Step 3: Verify litter appears in list
        list_response = await client.get("/api/litters/")
        assert list_response.status_code == 200
        litters_list = list_response.json()
        
        litter_ids = [l["id"] for l in litters_list]
        assert litter_id in litter_ids
        
        # Step 4: Update the litter
        update_data = {
            "description": "Updated lifecycle litter",
            "is_active": False
        }
        
        update_response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        assert update_response.status_code == 200
        updated_litter = update_response.json()
        
        assert updated_litter["id"] == litter_id
        assert updated_litter["description"] == update_data["description"]
        assert updated_litter["is_active"] == update_data["is_active"]
        assert updated_litter["date_of_litter"] == create_data["date_of_litter"]  # Unchanged
        
        # Step 5: Delete the litter
        delete_response = await client.delete(f"/api/litters/{litter_id}")
        assert delete_response.status_code == 204
        
        # Step 6: Verify litter is deleted
        final_get_response = await client.get(f"/api/litters/{litter_id}")
        assert final_get_response.status_code == 404
        
        # Step 7: Verify litter is not in list
        final_list_response = await client.get("/api/litters/")
        assert final_list_response.status_code == 200
        final_litters_list = final_list_response.json()
        
        final_litter_ids = [l["id"] for l in final_litters_list]
        assert litter_id not in final_litter_ids



class TestLitterPetAssignment:
    """Integration tests for assigning parent pets to litters."""

    @pytest.mark.asyncio
    async def test_assign_pets_successful_assignment(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test successful assignment of two parent pets to a litter.
        
        Validates: Requirements 3.1, 5.1, 5.2, 5.3
        """
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create a location
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create a breed
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create a litter
        litter = Litter(
            description="Test litter for pet assignment",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create two parent pets with the same location
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign pets to litter
        assignment_data = {
            "pet_ids": [str(parent1.id), str(parent2.id)]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/assign-pets",
            json=assignment_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contains updated litter
        assert data["id"] == litter.id
        assert data["status"] == "InProcess"  # Status should change to InProcess
        assert data["parent_pets"] is not None
        assert len(data["parent_pets"]) == 2
        
        # Verify parent pets are in the response
        parent_pet_ids = {p["id"] for p in data["parent_pets"]}
        assert str(parent1.id) in parent_pet_ids
        assert str(parent2.id) in parent_pet_ids

    @pytest.mark.asyncio
    async def test_assign_pets_location_mismatch_rejection(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that assigning pets from different locations is rejected.
        
        Validates: Requirements 3.1
        """
        from app.models.location import Location
        
        # Create two different locations
        location1 = Location(
            user_id=test_user.id,
            name="Location 1",
            address1="123 Main St",
            city="City1",
            state="State1",
            country="Country1",
            zipcode="12345",
            location_type="pet"
        )
        location2 = Location(
            user_id=test_user.id,
            name="Location 2",
            address1="456 Oak Ave",
            city="City2",
            state="State2",
            country="Country2",
            zipcode="67890",
            location_type="pet"
        )
        async_session.add_all([location1, location2])
        await async_session.commit()
        await async_session.refresh(location1)
        await async_session.refresh(location2)
        
        # Create a litter
        litter = Litter(
            description="Test litter for location mismatch",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create two parent pets with DIFFERENT locations
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location1.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location2.id,  # Different location
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Attempt to assign pets with different locations
        assignment_data = {
            "pet_ids": [str(parent1.id), str(parent2.id)]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/assign-pets",
            json=assignment_data
        )
        
        # Should return 400 Bad Request
        assert response.status_code == 400
        error_data = response.json()
        assert "location" in error_data["detail"].lower()
        
        # Verify litter status is still "Started"
        await async_session.refresh(litter)
        assert litter.status == "Started"

    @pytest.mark.asyncio
    async def test_assign_pets_invalid_pet_ids(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that assigning non-existent pet IDs is rejected.
        
        Validates: Requirements 5.1, 5.2
        """
        import uuid
        
        # Create a litter
        litter = Litter(
            description="Test litter for invalid pets",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Attempt to assign non-existent pets
        assignment_data = {
            "pet_ids": [str(uuid.uuid4()), str(uuid.uuid4())]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/assign-pets",
            json=assignment_data
        )
        
        # Should return 400 Bad Request
        assert response.status_code == 400
        error_data = response.json()
        assert "exist" in error_data["detail"].lower()

    @pytest.mark.asyncio
    async def test_assign_pets_status_change_to_inprocess(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that litter status changes to InProcess after pet assignment.
        
        Validates: Requirements 2.2, 5.3
        """
        from app.models.location import Location
        
        # Create a location
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create a litter with status "Started"
        litter = Litter(
            description="Test litter for status change",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Verify initial status
        assert litter.status == "Started"
        
        # Create two parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign pets to litter
        assignment_data = {
            "pet_ids": [str(parent1.id), str(parent2.id)]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/assign-pets",
            json=assignment_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify status changed to InProcess
        assert data["status"] == "InProcess"
        
        # Verify in database
        await async_session.refresh(litter)
        assert litter.status == "InProcess"

    @pytest.mark.asyncio
    async def test_assign_pets_nonexistent_litter(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that assigning pets to a non-existent litter returns 404.
        
        Validates: Requirements 5.1
        """
        import uuid
        
        # Create two pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Attempt to assign pets to non-existent litter
        non_existent_litter_id = 999999
        assignment_data = {
            "pet_ids": [str(parent1.id), str(parent2.id)]
        }
        
        response = await client.post(
            f"/api/litters/{non_existent_litter_id}/assign-pets",
            json=assignment_data
        )
        
        # Should return 404 Not Found
        assert response.status_code == 404



class TestAddPuppies:
    """Integration tests for adding puppies to litters."""

    @pytest.mark.asyncio
    async def test_add_puppies_successful(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test successfully adding puppies to a litter.
        
        Validates: Requirements 6.3, 6.4
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create a litter with status "InProcess"
        litter = Litter(
            description="Test litter for puppies",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create and assign parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Add puppies
        puppies_data = {
            "puppies": [
                {
                    "name": "Puppy 1",
                    "gender": "Male",
                    "birth_date": "2024-01-15",
                    "microchip": "123456789"
                },
                {
                    "name": "Puppy 2",
                    "gender": "Female",
                    "birth_date": "2024-01-15",
                    "microchip": "987654321"
                },
                {
                    "name": "Puppy 3",
                    "gender": "Male",
                    "birth_date": "2024-01-15"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/add-puppies",
            json=puppies_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contains puppies
        assert "puppies" in data
        assert data["puppies"] is not None
        assert len(data["puppies"]) == 3
        
        # Verify puppy details
        puppy_names = [p["name"] for p in data["puppies"]]
        assert "Puppy 1" in puppy_names
        assert "Puppy 2" in puppy_names
        assert "Puppy 3" in puppy_names
        
        # Verify puppies have correct attributes
        for puppy in data["puppies"]:
            assert "id" in puppy
            assert "name" in puppy
            assert "gender" in puppy
            assert "birth_date" in puppy
            assert puppy["gender"] in ["Male", "Female"]

    @pytest.mark.asyncio
    async def test_add_puppies_status_change_to_done(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that litter status changes to Done after adding puppies.
        
        Validates: Requirements 6.3
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create a litter with status "InProcess"
        litter = Litter(
            description="Test litter for status change",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Verify initial status
        assert litter.status == "InProcess"
        
        # Create and assign parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Add puppies
        puppies_data = {
            "puppies": [
                {
                    "name": "Puppy 1",
                    "gender": "Male",
                    "birth_date": "2024-01-15"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/add-puppies",
            json=puppies_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify status changed to Done
        assert data["status"] == "Done"
        
        # Verify in database
        await async_session.refresh(litter)
        assert litter.status == "Done"

    @pytest.mark.asyncio
    async def test_add_puppies_validation_no_parent_pets(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that adding puppies fails when litter has no parent pets assigned.
        
        Validates: Requirements 6.1
        """
        # Create a litter without parent pets
        litter = Litter(
            description="Test litter without parents",
            status="Started"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Attempt to add puppies
        puppies_data = {
            "puppies": [
                {
                    "name": "Puppy 1",
                    "gender": "Male",
                    "birth_date": "2024-01-15"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/add-puppies",
            json=puppies_data
        )
        
        # Should return 400 Bad Request
        assert response.status_code == 400
        error_data = response.json()
        assert "parent pets" in error_data["detail"].lower()

    @pytest.mark.asyncio
    async def test_add_puppies_data_persistence(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that puppy data is correctly persisted to the database.
        
        Validates: Requirements 6.4
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        from app.models.breed import Breed
        from sqlalchemy import select
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        breed = Breed(name="Test Breed", code="TB")
        async_session.add(breed)
        await async_session.commit()
        await async_session.refresh(breed)
        
        # Create a litter with parent pets
        litter = Litter(
            description="Test litter for persistence",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create and assign parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            breed_id=breed.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            breed_id=breed.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Add puppies
        puppies_data = {
            "puppies": [
                {
                    "name": "Persistent Puppy",
                    "gender": "Female",
                    "birth_date": "2024-01-15",
                    "microchip": "PERSIST123"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/add-puppies",
            json=puppies_data
        )
        
        assert response.status_code == 200
        
        # Query database directly to verify persistence
        query = select(Pet).where(Pet.litter_id == litter.id)
        result = await async_session.execute(query)
        puppies = result.scalars().all()
        
        # Verify puppy was persisted
        assert len(puppies) == 1
        puppy = puppies[0]
        assert puppy.name == "Persistent Puppy"
        assert puppy.gender == "Female"
        assert puppy.microchip == "PERSIST123"
        assert puppy.litter_id == litter.id
        assert puppy.location_id == location.id  # Derived from parent
        assert puppy.breed_id == breed.id  # Derived from parent
        assert puppy.user_id == test_user.id  # Derived from parent
        assert puppy.is_puppy is True

    @pytest.mark.asyncio
    async def test_add_puppies_nonexistent_litter(
        self,
        client: AsyncClient
    ):
        """
        Test that adding puppies to a non-existent litter returns 404.
        
        Validates: Requirements 6.1
        """
        # Attempt to add puppies to non-existent litter
        non_existent_litter_id = 999999
        puppies_data = {
            "puppies": [
                {
                    "name": "Puppy 1",
                    "gender": "Male",
                    "birth_date": "2024-01-15"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{non_existent_litter_id}/add-puppies",
            json=puppies_data
        )
        
        # Should return 404 Not Found
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_puppies_invalid_gender(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that adding puppies with invalid gender fails validation.
        
        Validates: Requirements 6.2
        """
        from app.models.litter_pet import LitterPet
        from app.models.location import Location
        
        # Create test data
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="City",
            state="State",
            country="Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create a litter with parent pets
        litter = Litter(
            description="Test litter for validation",
            status="InProcess"
        )
        async_session.add(litter)
        await async_session.commit()
        await async_session.refresh(litter)
        
        # Create and assign parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Assign parent pets to litter
        litter_pet1 = LitterPet(litter_id=litter.id, pet_id=parent1.id)
        litter_pet2 = LitterPet(litter_id=litter.id, pet_id=parent2.id)
        async_session.add_all([litter_pet1, litter_pet2])
        await async_session.commit()
        
        # Attempt to add puppies with invalid gender
        puppies_data = {
            "puppies": [
                {
                    "name": "Invalid Puppy",
                    "gender": "Unknown",  # Invalid gender
                    "birth_date": "2024-01-15"
                }
            ]
        }
        
        response = await client.post(
            f"/api/litters/{litter.id}/add-puppies",
            json=puppies_data
        )
        
        # Should return 422 Unprocessable Entity (validation error)
        assert response.status_code == 422



class TestMultiLitterPetAssignment:
    """Integration tests for multi-litter pet assignment."""

    @pytest.mark.asyncio
    async def test_same_pet_can_be_assigned_to_multiple_litters(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that the same pet can be assigned to multiple litters.
        
        This verifies that the litter_pets junction table has no unique
        constraints that would prevent multi-litter assignment.
        
        Validates: Requirements 5.5, 11.1, 11.2, 11.3, 11.4
        """
        from app.models.location import Location
        from app.models.litter_pet import LitterPet
        from sqlalchemy import select
        
        # Create a location
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="Test City",
            state="Test State",
            country="Test Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create two parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Create three litters
        litter1 = Litter(
            description="Litter 1",
            status="Started",
            is_active=True
        )
        litter2 = Litter(
            description="Litter 2",
            status="Started",
            is_active=True
        )
        litter3 = Litter(
            description="Litter 3",
            status="Started",
            is_active=True
        )
        async_session.add_all([litter1, litter2, litter3])
        await async_session.commit()
        await async_session.refresh(litter1)
        await async_session.refresh(litter2)
        await async_session.refresh(litter3)
        
        # Assign the same two pets to all three litters
        response1 = await client.post(
            f"/api/litters/{litter1.id}/assign-pets",
            json={"pet_ids": [str(parent1.id), str(parent2.id)]}
        )
        assert response1.status_code == 200, \
            f"First assignment failed: {response1.json()}"
        
        response2 = await client.post(
            f"/api/litters/{litter2.id}/assign-pets",
            json={"pet_ids": [str(parent1.id), str(parent2.id)]}
        )
        assert response2.status_code == 200, \
            f"Second assignment failed: {response2.json()}"
        
        response3 = await client.post(
            f"/api/litters/{litter3.id}/assign-pets",
            json={"pet_ids": [str(parent1.id), str(parent2.id)]}
        )
        assert response3.status_code == 200, \
            f"Third assignment failed: {response3.json()}"
        
        # Verify all three litters have the same pets assigned
        query = select(LitterPet).where(LitterPet.pet_id == parent1.id)
        result = await async_session.execute(query)
        parent1_assignments = result.scalars().all()
        
        assert len(parent1_assignments) == 3, \
            f"Parent 1 should be assigned to 3 litters, got {len(parent1_assignments)}"
        
        query = select(LitterPet).where(LitterPet.pet_id == parent2.id)
        result = await async_session.execute(query)
        parent2_assignments = result.scalars().all()
        
        assert len(parent2_assignments) == 3, \
            f"Parent 2 should be assigned to 3 litters, got {len(parent2_assignments)}"
        
        # Verify each litter has both pets assigned
        for litter_id in [litter1.id, litter2.id, litter3.id]:
            query = select(LitterPet).where(LitterPet.litter_id == litter_id)
            result = await async_session.execute(query)
            litter_pets = result.scalars().all()
            
            assert len(litter_pets) == 2, \
                f"Litter {litter_id} should have 2 pets assigned, got {len(litter_pets)}"
            
            pet_ids = {lp.pet_id for lp in litter_pets}
            assert parent1.id in pet_ids, \
                f"Parent 1 should be assigned to litter {litter_id}"
            assert parent2.id in pet_ids, \
                f"Parent 2 should be assigned to litter {litter_id}"
        
        # Verify all litters have status "InProcess"
        await async_session.refresh(litter1)
        await async_session.refresh(litter2)
        await async_session.refresh(litter3)
        
        assert litter1.status == "InProcess", \
            f"Litter 1 should have status 'InProcess', got '{litter1.status}'"
        assert litter2.status == "InProcess", \
            f"Litter 2 should have status 'InProcess', got '{litter2.status}'"
        assert litter3.status == "InProcess", \
            f"Litter 3 should have status 'InProcess', got '{litter3.status}'"

    @pytest.mark.asyncio
    async def test_pet_available_for_assignment_even_when_assigned_to_other_litters(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that pets already assigned to litters remain available for assignment to new litters.
        
        Validates: Requirements 11.2
        """
        from app.models.location import Location
        
        # Create a location
        location = Location(
            user_id=test_user.id,
            name="Test Location",
            address1="123 Main St",
            city="Test City",
            state="Test State",
            country="Test Country",
            zipcode="12345",
            location_type="pet"
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Create two parent pets
        parent1 = Pet(
            user_id=test_user.id,
            name="Parent 1",
            location_id=location.id,
            gender="Male",
            is_puppy=False
        )
        parent2 = Pet(
            user_id=test_user.id,
            name="Parent 2",
            location_id=location.id,
            gender="Female",
            is_puppy=False
        )
        async_session.add_all([parent1, parent2])
        await async_session.commit()
        await async_session.refresh(parent1)
        await async_session.refresh(parent2)
        
        # Create first litter and assign pets
        litter1 = Litter(
            description="First Litter",
            status="Started",
            is_active=True
        )
        async_session.add(litter1)
        await async_session.commit()
        await async_session.refresh(litter1)
        
        response1 = await client.post(
            f"/api/litters/{litter1.id}/assign-pets",
            json={"pet_ids": [str(parent1.id), str(parent2.id)]}
        )
        assert response1.status_code == 200
        
        # Create second litter
        litter2 = Litter(
            description="Second Litter",
            status="Started",
            is_active=True
        )
        async_session.add(litter2)
        await async_session.commit()
        await async_session.refresh(litter2)
        
        # Attempt to assign the same pets to the second litter
        # This should succeed because multi-litter assignment is allowed
        response2 = await client.post(
            f"/api/litters/{litter2.id}/assign-pets",
            json={"pet_ids": [str(parent1.id), str(parent2.id)]}
        )
        
        assert response2.status_code == 200, \
            f"Assigning already-assigned pets should succeed, got {response2.status_code}: {response2.json()}"
        
        # Verify both litters have the same pets assigned
        data1 = response1.json()
        data2 = response2.json()
        
        assert len(data1["parent_pets"]) == 2
        assert len(data2["parent_pets"]) == 2
        
        # Both litters should have the same parent pet IDs
        parent_ids_1 = {pet["id"] for pet in data1["parent_pets"]}
        parent_ids_2 = {pet["id"] for pet in data2["parent_pets"]}
        
        assert parent_ids_1 == parent_ids_2, \
            "Both litters should have the same parent pets"
