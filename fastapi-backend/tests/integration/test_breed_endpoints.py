"""Integration tests for breeds API endpoints.

Tests the complete breed management workflow including:
- Creating breeds
- Listing breeds
- Getting single breed
- Updating breeds
- Deleting breeds
- Duplicate name validation
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.models.breed import Breed


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


class TestBreedCreation:
    """Integration tests for breed creation."""

    @pytest.mark.asyncio
    async def test_create_breed_with_all_fields(self, client: AsyncClient):
        """
        Test creating a breed with all fields populated.
        
        Validates: Requirements 6.1, 13.3
        """
        breed_data = {
            "name": "Golden Retriever",
            "code": "GR001",
            "group": "Sporting Group"
        }
        
        response = await client.post("/api/breeds/", json=breed_data)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response contains all fields
        assert "id" in data
        assert data["name"] == breed_data["name"]
        assert data["code"] == breed_data["code"]
        assert data["group"] == breed_data["group"]
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_breed_with_minimal_fields(self, client: AsyncClient):
        """
        Test creating a breed with only required fields.
        
        Validates: Requirements 6.1, 13.3
        """
        breed_data = {
            "name": "Labrador Retriever"
        }
        
        response = await client.post("/api/breeds/", json=breed_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert "id" in data
        assert data["name"] == breed_data["name"]
        assert data["code"] is None
        assert data["group"] is None

    @pytest.mark.asyncio
    async def test_create_breed_duplicate_name_fails(self, client: AsyncClient):
        """
        Test that creating a breed with duplicate name fails.
        
        Validates: Requirements 6.1, 13.3
        """
        breed_data = {
            "name": "Beagle",
            "code": "BG001"
        }
        
        # Create first breed
        response1 = await client.post("/api/breeds/", json=breed_data)
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = await client.post("/api/breeds/", json=breed_data)
        assert response2.status_code == 400
        
        data = response2.json()
        assert "detail" in data
        assert "already exists" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_breed_missing_name_fails(self, client: AsyncClient):
        """
        Test that creating a breed without name fails validation.
        
        Validates: Requirements 6.1, 13.3
        """
        breed_data = {
            "code": "TEST001"
        }
        
        response = await client.post("/api/breeds/", json=breed_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_breed_empty_name_fails(self, client: AsyncClient):
        """
        Test that creating a breed with empty name fails validation.
        
        Validates: Requirements 6.1, 13.3
        """
        breed_data = {
            "name": ""
        }
        
        response = await client.post("/api/breeds/", json=breed_data)
        assert response.status_code == 422  # Validation error


class TestBreedListing:
    """Integration tests for listing breeds."""

    @pytest.mark.asyncio
    async def test_list_breeds_empty(self, client: AsyncClient):
        """
        Test listing breeds when database is empty.
        
        Validates: Requirements 6.1, 13.3
        """
        response = await client.get("/api/breeds/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # May have breeds from other tests, so just check it's a list

    @pytest.mark.asyncio
    async def test_list_breeds_with_data(self, client: AsyncClient):
        """
        Test listing breeds with multiple breeds in database.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create multiple breeds
        breeds_data = [
            {"name": "Poodle", "code": "PD001", "group": "Non-Sporting"},
            {"name": "Bulldog", "code": "BD001", "group": "Non-Sporting"},
            {"name": "Chihuahua", "code": "CH001", "group": "Toy"}
        ]
        
        created_ids = []
        for breed_data in breeds_data:
            response = await client.post("/api/breeds/", json=breed_data)
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
        
        # List all breeds
        response = await client.get("/api/breeds/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= len(breeds_data)
        
        # Verify our created breeds are in the list
        breed_names = [b["name"] for b in data]
        for breed_data in breeds_data:
            assert breed_data["name"] in breed_names

    @pytest.mark.asyncio
    async def test_list_breeds_alphabetical_order(self, client: AsyncClient):
        """
        Test that breeds are returned in alphabetical order by name.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create breeds with names that will test ordering
        breeds_data = [
            {"name": "Zebra Hound"},  # Should be last
            {"name": "Aardvark Terrier"},  # Should be first
            {"name": "Midway Spaniel"}  # Should be middle
        ]
        
        for breed_data in breeds_data:
            await client.post("/api/breeds/", json=breed_data)
        
        # List breeds
        response = await client.get("/api/breeds/")
        assert response.status_code == 200
        data = response.json()
        
        # Find our test breeds in the response
        test_breeds = [b for b in data if b["name"] in [bd["name"] for bd in breeds_data]]
        
        # Verify they're in alphabetical order
        assert len(test_breeds) == 3
        names = [b["name"] for b in test_breeds]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_breeds_pagination(self, client: AsyncClient):
        """
        Test breed listing with pagination parameters.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create several breeds
        for i in range(5):
            breed_data = {"name": f"Pagination Test Breed {i:02d}"}
            await client.post("/api/breeds/", json=breed_data)
        
        # Test with limit
        response = await client.get("/api/breeds/?limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 3
        
        # Test with skip
        response = await client.get("/api/breeds/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2


class TestBreedRetrieval:
    """Integration tests for retrieving single breed."""

    @pytest.mark.asyncio
    async def test_get_breed_by_id(self, client: AsyncClient):
        """
        Test getting a single breed by ID.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create a breed
        breed_data = {
            "name": "Dachshund",
            "code": "DH001",
            "group": "Hound Group"
        }
        
        create_response = await client.post("/api/breeds/", json=breed_data)
        assert create_response.status_code == 201
        created_breed = create_response.json()
        breed_id = created_breed["id"]
        
        # Get the breed
        response = await client.get(f"/api/breeds/{breed_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == breed_id
        assert data["name"] == breed_data["name"]
        assert data["code"] == breed_data["code"]
        assert data["group"] == breed_data["group"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_breed_returns_404(self, client: AsyncClient):
        """
        Test that getting a non-existent breed returns 404.
        
        Validates: Requirements 6.1, 13.3
        """
        # Use a very high ID that shouldn't exist
        response = await client.get("/api/breeds/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestBreedUpdate:
    """Integration tests for updating breeds."""

    @pytest.mark.asyncio
    async def test_update_breed_all_fields(self, client: AsyncClient):
        """
        Test updating all fields of a breed.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create a breed
        breed_data = {
            "name": "Original Name",
            "code": "ORIG001",
            "group": "Original Group"
        }
        
        create_response = await client.post("/api/breeds/", json=breed_data)
        assert create_response.status_code == 201
        breed_id = create_response.json()["id"]
        
        # Update the breed
        update_data = {
            "name": "Updated Name",
            "code": "UPD001",
            "group": "Updated Group"
        }
        
        response = await client.put(f"/api/breeds/{breed_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == breed_id
        assert data["name"] == update_data["name"]
        assert data["code"] == update_data["code"]
        assert data["group"] == update_data["group"]

    @pytest.mark.asyncio
    async def test_update_breed_partial_fields(self, client: AsyncClient):
        """
        Test updating only some fields of a breed.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create a breed
        breed_data = {
            "name": "Partial Update Test",
            "code": "PUT001",
            "group": "Test Group"
        }
        
        create_response = await client.post("/api/breeds/", json=breed_data)
        assert create_response.status_code == 201
        created_breed = create_response.json()
        breed_id = created_breed["id"]
        
        # Update only the name
        update_data = {
            "name": "Updated Partial Name"
        }
        
        response = await client.put(f"/api/breeds/{breed_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == breed_id
        assert data["name"] == update_data["name"]
        # Other fields should remain unchanged
        assert data["code"] == breed_data["code"]
        assert data["group"] == breed_data["group"]

    @pytest.mark.asyncio
    async def test_update_breed_duplicate_name_fails(self, client: AsyncClient):
        """
        Test that updating a breed to a duplicate name fails.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create two breeds
        breed1_data = {"name": "Breed One"}
        breed2_data = {"name": "Breed Two"}
        
        response1 = await client.post("/api/breeds/", json=breed1_data)
        assert response1.status_code == 201
        
        response2 = await client.post("/api/breeds/", json=breed2_data)
        assert response2.status_code == 201
        breed2_id = response2.json()["id"]
        
        # Try to update breed2 to have the same name as breed1
        update_data = {"name": "Breed One"}
        
        response = await client.put(f"/api/breeds/{breed2_id}", json=update_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "already exists" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_nonexistent_breed_returns_404(self, client: AsyncClient):
        """
        Test that updating a non-existent breed returns 404.
        
        Validates: Requirements 6.1, 13.3
        """
        update_data = {"name": "Updated Name"}
        
        response = await client.put("/api/breeds/999999", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestBreedDeletion:
    """Integration tests for deleting breeds."""

    @pytest.mark.asyncio
    async def test_delete_breed(self, client: AsyncClient):
        """
        Test deleting a breed.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create a breed
        breed_data = {"name": "Breed To Delete"}
        
        create_response = await client.post("/api/breeds/", json=breed_data)
        assert create_response.status_code == 201
        breed_id = create_response.json()["id"]
        
        # Delete the breed
        response = await client.delete(f"/api/breeds/{breed_id}")
        
        assert response.status_code == 204
        
        # Verify breed is gone
        get_response = await client.get(f"/api/breeds/{breed_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_breed_returns_404(self, client: AsyncClient):
        """
        Test that deleting a non-existent breed returns 404.
        
        Validates: Requirements 6.1, 13.3
        """
        response = await client.delete("/api/breeds/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestBreedManagementWorkflow:
    """Integration tests for complete breed management workflow."""

    @pytest.mark.asyncio
    async def test_complete_breed_lifecycle(self, client: AsyncClient):
        """
        Test complete breed management workflow: create, read, update, delete.
        
        Validates: Requirements 6.1, 13.3
        """
        # Step 1: Create a breed
        create_data = {
            "name": "Lifecycle Test Breed",
            "code": "LTB001",
            "group": "Test Group"
        }
        
        create_response = await client.post("/api/breeds/", json=create_data)
        assert create_response.status_code == 201
        created_breed = create_response.json()
        breed_id = created_breed["id"]
        
        assert created_breed["name"] == create_data["name"]
        assert created_breed["code"] == create_data["code"]
        assert created_breed["group"] == create_data["group"]
        
        # Step 2: Read the breed
        get_response = await client.get(f"/api/breeds/{breed_id}")
        assert get_response.status_code == 200
        retrieved_breed = get_response.json()
        
        assert retrieved_breed["id"] == breed_id
        assert retrieved_breed["name"] == create_data["name"]
        
        # Step 3: Verify breed appears in list
        list_response = await client.get("/api/breeds/")
        assert list_response.status_code == 200
        breeds_list = list_response.json()
        
        breed_ids = [b["id"] for b in breeds_list]
        assert breed_id in breed_ids
        
        # Step 4: Update the breed
        update_data = {
            "name": "Updated Lifecycle Breed",
            "code": "ULB001"
        }
        
        update_response = await client.put(f"/api/breeds/{breed_id}", json=update_data)
        assert update_response.status_code == 200
        updated_breed = update_response.json()
        
        assert updated_breed["id"] == breed_id
        assert updated_breed["name"] == update_data["name"]
        assert updated_breed["code"] == update_data["code"]
        assert updated_breed["group"] == create_data["group"]  # Unchanged
        
        # Step 5: Delete the breed
        delete_response = await client.delete(f"/api/breeds/{breed_id}")
        assert delete_response.status_code == 204
        
        # Step 6: Verify breed is deleted
        final_get_response = await client.get(f"/api/breeds/{breed_id}")
        assert final_get_response.status_code == 404
        
        # Step 7: Verify breed is not in list
        final_list_response = await client.get("/api/breeds/")
        assert final_list_response.status_code == 200
        final_breeds_list = final_list_response.json()
        
        final_breed_ids = [b["id"] for b in final_breeds_list]
        assert breed_id not in final_breed_ids

    @pytest.mark.asyncio
    async def test_multiple_breeds_management(self, client: AsyncClient):
        """
        Test managing multiple breeds simultaneously.
        
        Validates: Requirements 6.1, 13.3
        """
        # Create multiple breeds
        breeds_data = [
            {"name": "Multi Breed 1", "code": "MB001", "group": "Group A"},
            {"name": "Multi Breed 2", "code": "MB002", "group": "Group B"},
            {"name": "Multi Breed 3", "code": "MB003", "group": "Group A"}
        ]
        
        created_breeds = []
        for breed_data in breeds_data:
            response = await client.post("/api/breeds/", json=breed_data)
            assert response.status_code == 201
            created_breeds.append(response.json())
        
        # Verify all breeds exist
        list_response = await client.get("/api/breeds/")
        assert list_response.status_code == 200
        all_breeds = list_response.json()
        
        created_ids = [b["id"] for b in created_breeds]
        all_ids = [b["id"] for b in all_breeds]
        
        for breed_id in created_ids:
            assert breed_id in all_ids
        
        # Update one breed
        update_data = {"name": "Updated Multi Breed 2"}
        update_response = await client.put(
            f"/api/breeds/{created_breeds[1]['id']}",
            json=update_data
        )
        assert update_response.status_code == 200
        
        # Delete one breed
        delete_response = await client.delete(f"/api/breeds/{created_breeds[0]['id']}")
        assert delete_response.status_code == 204
        
        # Verify final state
        final_list_response = await client.get("/api/breeds/")
        assert final_list_response.status_code == 200
        final_breeds = final_list_response.json()
        final_ids = [b["id"] for b in final_breeds]
        
        # First breed should be deleted
        assert created_breeds[0]["id"] not in final_ids
        
        # Second and third breeds should still exist
        assert created_breeds[1]["id"] in final_ids
        assert created_breeds[2]["id"] in final_ids
        
        # Verify second breed was updated
        updated_breed = next(b for b in final_breeds if b["id"] == created_breeds[1]["id"])
        assert updated_breed["name"] == update_data["name"]
