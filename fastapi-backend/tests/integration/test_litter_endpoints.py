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
    async def test_create_litter_with_all_fields(self, client: AsyncClient):
        """
        Test creating a litter with all fields populated.
        
        Validates: Requirements 7.1, 13.4
        """
        litter_data = {
            "date_of_litter": str(date.today()),
            "description": "Test litter with all fields",
            "is_active": True
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response contains all fields
        assert "id" in data
        assert data["date_of_litter"] == litter_data["date_of_litter"]
        assert data["description"] == litter_data["description"]
        assert data["is_active"] == litter_data["is_active"]
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_litter_with_minimal_fields(self, client: AsyncClient):
        """
        Test creating a litter with only required fields.
        
        Validates: Requirements 7.1, 13.4
        """
        litter_data = {
            "date_of_litter": str(date.today())
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert "id" in data
        assert data["date_of_litter"] == litter_data["date_of_litter"]
        assert data["description"] is None
        assert data["is_active"] is True  # Default value

    @pytest.mark.asyncio
    async def test_create_litter_missing_date_fails(self, client: AsyncClient):
        """
        Test that creating a litter without date fails validation.
        
        Validates: Requirements 7.1, 13.4
        """
        litter_data = {
            "description": "Missing date"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_litter_with_past_date(self, client: AsyncClient):
        """
        Test creating a litter with a past date.
        
        Validates: Requirements 7.1, 13.4
        """
        past_date = date.today() - timedelta(days=30)
        litter_data = {
            "date_of_litter": str(past_date),
            "description": "Litter from 30 days ago"
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["date_of_litter"] == str(past_date)

    @pytest.mark.asyncio
    async def test_create_litter_inactive(self, client: AsyncClient):
        """
        Test creating an inactive litter.
        
        Validates: Requirements 7.1, 13.4
        """
        litter_data = {
            "date_of_litter": str(date.today()),
            "description": "Inactive litter",
            "is_active": False
        }
        
        response = await client.post("/api/litters/", json=litter_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["is_active"] is False


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
            {"date_of_litter": str(date.today()), "description": "Litter 1"},
            {"date_of_litter": str(date.today() - timedelta(days=10)), "description": "Litter 2"},
            {"date_of_litter": str(date.today() - timedelta(days=20)), "description": "Litter 3"}
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
    async def test_list_litters_chronological_order(self, client: AsyncClient):
        """
        Test that litters are returned in chronological order (most recent first).
        
        Validates: Requirements 7.1, 13.4
        """
        # Create litters with different dates
        litters_data = [
            {"date_of_litter": str(date.today() - timedelta(days=30)), "description": "Oldest"},
            {"date_of_litter": str(date.today()), "description": "Newest"},
            {"date_of_litter": str(date.today() - timedelta(days=15)), "description": "Middle"}
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
        # Create active and inactive litters
        active_litter = {
            "date_of_litter": str(date.today()),
            "description": "Active litter",
            "is_active": True
        }
        inactive_litter = {
            "date_of_litter": str(date.today() - timedelta(days=5)),
            "description": "Inactive litter",
            "is_active": False
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
                "date_of_litter": str(date.today() - timedelta(days=i)),
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
    async def test_get_litter_by_id(self, client: AsyncClient):
        """
        Test getting a single litter by ID.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "date_of_litter": str(date.today()),
            "description": "Test litter for retrieval",
            "is_active": True
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
        assert data["date_of_litter"] == litter_data["date_of_litter"]
        assert data["description"] == litter_data["description"]
        assert data["is_active"] == litter_data["is_active"]

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
    async def test_update_litter_all_fields(self, client: AsyncClient):
        """
        Test updating all fields of a litter.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "date_of_litter": str(date.today() - timedelta(days=10)),
            "description": "Original description",
            "is_active": True
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        litter_id = create_response.json()["id"]
        
        # Update the litter
        update_data = {
            "date_of_litter": str(date.today()),
            "description": "Updated description",
            "is_active": False
        }
        
        response = await client.put(f"/api/litters/{litter_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == litter_id
        assert data["date_of_litter"] == update_data["date_of_litter"]
        assert data["description"] == update_data["description"]
        assert data["is_active"] == update_data["is_active"]

    @pytest.mark.asyncio
    async def test_update_litter_partial_fields(self, client: AsyncClient):
        """
        Test updating only some fields of a litter.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "date_of_litter": str(date.today()),
            "description": "Partial update test",
            "is_active": True
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
        # Other fields should remain unchanged
        assert data["date_of_litter"] == litter_data["date_of_litter"]
        assert data["is_active"] == litter_data["is_active"]

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
    async def test_delete_litter(self, client: AsyncClient):
        """
        Test deleting a litter.
        
        Validates: Requirements 7.1, 13.4
        """
        # Create a litter
        litter_data = {
            "date_of_litter": str(date.today()),
            "description": "Litter to delete"
        }
        
        create_response = await client.post("/api/litters/", json=litter_data)
        assert create_response.status_code == 201
        litter_id = create_response.json()["id"]
        
        # Delete the litter
        response = await client.delete(f"/api/litters/{litter_id}")
        
        assert response.status_code == 204
        
        # Verify litter is gone
        get_response = await client.get(f"/api/litters/{litter_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_litter_returns_404(self, client: AsyncClient):
        """
        Test that deleting a non-existent litter returns 404.
        
        Validates: Requirements 7.1, 13.4
        """
        response = await client.delete("/api/litters/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


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
            "date_of_litter": str(date.today()),
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
            "date_of_litter": str(date.today()),
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
            "date_of_litter": str(date.today()),
            "description": "Lifecycle test litter",
            "is_active": True
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

