"""
End-to-end integration tests for complete breeding lifecycle workflows.

These tests verify complete user journeys through the breeding management system,
testing multiple endpoints in sequence to ensure the entire system works together correctly.

Task 21: Integration End-to-End Tests
Requirements: 1.1, 2.1, 2.2, 2.3, 3.1, 4.1, 5.1, 6.1, 10.1
"""

import pytest
from datetime import date
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.breed import Breed
from app.models.location import Location


@pytest.mark.asyncio
async def test_complete_litter_lifecycle_workflow(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Test complete breeding lifecycle: create → assign pets → add puppies.
    
    This end-to-end test verifies the most common breeding management journey:
    1. Create a new breeding (status: Started)
    2. Assign two parent pets to the breeding (status: InProcess)
    3. Add puppies to the breeding (status: Done)
    4. Verify all data is correctly persisted and retrievable
    
    Requirements: 1.1, 2.1, 2.2, 2.3, 4.1, 5.1, 6.1
    """
    from app.models.location import Location
    from app.models.breed import Breed
    from app.models.pet import Pet
    
    # Setup: Create location and breed
    location = Location(
        user_id=test_user.id,
        name="E2E Test Kennel",
        address1="123 Test St",
        city="Test City",
        state="Test State",
        country="Test Country",
        zipcode="12345",
        location_type="pet"
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    breed = Breed(name="E2E Test Breed", code="E2E")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Create two parent pets at the same location
    parent1 = Pet(
        user_id=test_user.id,
        name="Parent Dog 1",
        location_id=location.id,
        breed_id=breed.id,
        gender="Male",
        is_puppy=False
    )
    parent2 = Pet(
        user_id=test_user.id,
        name="Parent Dog 2",
        location_id=location.id,
        breed_id=breed.id,
        gender="Female",
        is_puppy=False
    )
    async_session.add_all([parent1, parent2])
    await async_session.commit()
    await async_session.refresh(parent1)
    await async_session.refresh(parent2)
    
    # Step 1: Create a new breeding
    breeding_data = {"description": "E2E Test Breeding"}
    create_response = await async_client.post("/api/breedings/", json=breeding_data)
    
    assert create_response.status_code == 201
    breeding = create_response.json()
    breeding_id = breeding["id"]
    
    # Verify initial state
    assert breeding["description"] == "E2E Test Breeding"
    assert breeding["status"] == "Started", "New breeding should have status 'Started'"
    assert breeding["parent_pets"] is None
    assert breeding["puppies"] is None
    
    # Step 2: Assign parent pets to the breeding
    assign_data = {"pet_ids": [str(parent1.id), str(parent2.id)]}
    assign_response = await async_client.post(
        f"/api/breedings/{breeding_id}/assign-pets",
        json=assign_data
    )
    
    assert assign_response.status_code == 200
    litter_with_parents = assign_response.json()
    
    # Verify status transition to InProcess
    assert litter_with_parents["status"] == "InProcess", "Breeding should be 'InProcess' after assigning pets"
    assert litter_with_parents["parent_pets"] is not None
    assert len(litter_with_parents["parent_pets"]) == 2
    
    parent_names = [p["name"] for p in litter_with_parents["parent_pets"]]
    assert "Parent Dog 1" in parent_names
    assert "Parent Dog 2" in parent_names
    
    # Step 3: Add puppies to the breeding
    puppies_data = {
        "puppies": [
            {
                "name": "Puppy 1",
                "gender": "Male",
                "birth_date": str(date.today()),
                "microchip": "E2E001"
            },
            {
                "name": "Puppy 2",
                "gender": "Female",
                "birth_date": str(date.today()),
                "microchip": "E2E002"
            },
            {
                "name": "Puppy 3",
                "gender": "Male",
                "birth_date": str(date.today()),
                "microchip": "E2E003"
            }
        ]
    }
    puppies_response = await async_client.post(
        f"/api/breedings/{breeding_id}/add-puppies",
        json=puppies_data
    )
    
    assert puppies_response.status_code == 200
    litter_with_puppies = puppies_response.json()
    
    # Verify status transition to Done
    assert litter_with_puppies["status"] == "Done", "Breeding should be 'Done' after adding puppies"
    assert litter_with_puppies["puppies"] is not None
    assert len(litter_with_puppies["puppies"]) == 3
    
    puppy_names = [p["name"] for p in litter_with_puppies["puppies"]]
    assert "Puppy 1" in puppy_names
    assert "Puppy 2" in puppy_names
    assert "Puppy 3" in puppy_names
    
    # Step 4: Verify complete breeding can be retrieved
    get_response = await async_client.get(f"/api/breedings/{breeding_id}")
    
    assert get_response.status_code == 200
    final_litter = get_response.json()
    
    # Verify all data is present
    assert final_litter["id"] == breeding_id
    assert final_litter["description"] == "E2E Test Breeding"
    assert final_litter["status"] == "Done"
    assert len(final_litter["parent_pets"]) == 2
    assert len(final_litter["puppies"]) == 3
    
    # Verify breeding appears in list
    list_response = await async_client.get("/api/breedings/")
    assert list_response.status_code == 200
    breedings = list_response.json()
    
    litter_ids = [l["id"] for l in breedings]
    assert breeding_id in litter_ids


@pytest.mark.asyncio
async def test_filter_functionality_workflow(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Test complete filter functionality across multiple breedings.
    
    This test verifies:
    1. Create multiple breedings with different locations, statuses, and breeds
    2. Filter by location
    3. Filter by status
    4. Filter by breed
    5. Filter by multiple criteria combined
    
    Requirements: 10.1
    """
    from app.models.location import Location
    from app.models.breed import Breed
    from app.models.pet import Pet
    from app.models.breeding import Breeding
    from app.models.breeding_pet import BreedingPet
    
    # Setup: Create two locations
    location1 = Location(
        user_id=test_user.id,
        name="Location 1",
        address1="123 Main St",
        city="City1",
        state="State1",
        country="Country1",
        zipcode="11111",
        location_type="pet"
    )
    location2 = Location(
        user_id=test_user.id,
        name="Location 2",
        address1="456 Oak Ave",
        city="City2",
        state="State2",
        country="Country2",
        zipcode="22222",
        location_type="pet"
    )
    async_session.add_all([location1, location2])
    await async_session.commit()
    await async_session.refresh(location1)
    await async_session.refresh(location2)
    
    # Setup: Create two breeds
    breed1 = Breed(name="Filter Breed 1", code="FB1")
    breed2 = Breed(name="Filter Breed 2", code="FB2")
    async_session.add_all([breed1, breed2])
    await async_session.commit()
    await async_session.refresh(breed1)
    await async_session.refresh(breed2)
    
    # Create breedings with different combinations
    # Breeding 1: Location1, Breed1, InProcess
    litter1 = Breeding(description="L1-B1-InProcess", status="InProcess")
    async_session.add(litter1)
    await async_session.commit()
    await async_session.refresh(litter1)
    
    pet1_1 = Pet(user_id=test_user.id, name="P1_1", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
    pet1_2 = Pet(user_id=test_user.id, name="P1_2", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
    async_session.add_all([pet1_1, pet1_2])
    await async_session.commit()
    await async_session.refresh(pet1_1)
    await async_session.refresh(pet1_2)
    
    lp1_1 = BreedingPet(breeding_id=litter1.id, pet_id=pet1_1.id)
    lp1_2 = BreedingPet(breeding_id=litter1.id, pet_id=pet1_2.id)
    async_session.add_all([lp1_1, lp1_2])
    await async_session.commit()
    
    # Breeding 2: Location1, Breed1, Done
    litter2 = Breeding(description="L1-B1-Done", status="Done")
    async_session.add(litter2)
    await async_session.commit()
    await async_session.refresh(litter2)
    
    pet2_1 = Pet(user_id=test_user.id, name="P2_1", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
    pet2_2 = Pet(user_id=test_user.id, name="P2_2", location_id=location1.id, breed_id=breed1.id, is_puppy=False)
    async_session.add_all([pet2_1, pet2_2])
    await async_session.commit()
    await async_session.refresh(pet2_1)
    await async_session.refresh(pet2_2)
    
    lp2_1 = BreedingPet(breeding_id=litter2.id, pet_id=pet2_1.id)
    lp2_2 = BreedingPet(breeding_id=litter2.id, pet_id=pet2_2.id)
    async_session.add_all([lp2_1, lp2_2])
    await async_session.commit()
    
    # Breeding 3: Location2, Breed2, InProcess
    litter3 = Breeding(description="L2-B2-InProcess", status="InProcess")
    async_session.add(litter3)
    await async_session.commit()
    await async_session.refresh(litter3)
    
    pet3_1 = Pet(user_id=test_user.id, name="P3_1", location_id=location2.id, breed_id=breed2.id, is_puppy=False)
    pet3_2 = Pet(user_id=test_user.id, name="P3_2", location_id=location2.id, breed_id=breed2.id, is_puppy=False)
    async_session.add_all([pet3_1, pet3_2])
    await async_session.commit()
    await async_session.refresh(pet3_1)
    await async_session.refresh(pet3_2)
    
    lp3_1 = BreedingPet(breeding_id=litter3.id, pet_id=pet3_1.id)
    lp3_2 = BreedingPet(breeding_id=litter3.id, pet_id=pet3_2.id)
    async_session.add_all([lp3_1, lp3_2])
    await async_session.commit()
    
    # Test 1: Filter by location1
    response = await async_client.get(f"/api/breedings/?location_id={str(location1.id)}")
    assert response.status_code == 200
    data = response.json()
    
    litter_ids = [l["id"] for l in data]
    assert litter1.id in litter_ids
    assert litter2.id in litter_ids
    assert litter3.id not in litter_ids
    
    # Test 2: Filter by InProcess status
    response = await async_client.get("/api/breedings/?status=InProcess")
    assert response.status_code == 200
    data = response.json()
    
    litter_ids = [l["id"] for l in data]
    assert litter1.id in litter_ids
    assert litter2.id not in litter_ids
    assert litter3.id in litter_ids
    
    # Test 3: Filter by breed1
    response = await async_client.get(f"/api/breedings/?breed_id={str(breed1.id)}")
    assert response.status_code == 200
    data = response.json()
    
    litter_ids = [l["id"] for l in data]
    assert litter1.id in litter_ids
    assert litter2.id in litter_ids
    assert litter3.id not in litter_ids
    
    # Test 4: Combined filters (location1 + breed1 + InProcess)
    response = await async_client.get(
        f"/api/breedings/?location_id={str(location1.id)}&breed_id={str(breed1.id)}&status=InProcess"
    )
    assert response.status_code == 200
    data = response.json()
    
    litter_ids = [l["id"] for l in data]
    assert litter1.id in litter_ids
    assert litter2.id not in litter_ids  # Wrong status
    assert litter3.id not in litter_ids  # Wrong location and breed


@pytest.mark.asyncio
async def test_multi_litter_pet_assignment_workflow(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Test that the same pet can be assigned to multiple breedings.
    
    This test verifies:
    1. Create two breedings
    2. Create two parent pets
    3. Assign the same pets to both breedings
    4. Verify both breedings have the same parent pets
    5. Verify pets can be retrieved and show multiple breeding assignments
    
    Requirements: 5.1, 11.1, 11.2, 11.3, 11.4
    """
    from app.models.location import Location
    from app.models.breed import Breed
    from app.models.pet import Pet
    from app.models.breeding import Breeding
    
    # Setup: Create location and breed
    location = Location(
        user_id=test_user.id,
        name="Multi-Breeding Location",
        address1="789 Multi St",
        city="Multi City",
        state="Multi State",
        country="Multi Country",
        zipcode="99999",
        location_type="pet"
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    breed = Breed(name="Multi-Breeding Breed", code="MLB")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Create two parent pets
    parent1 = Pet(
        user_id=test_user.id,
        name="Multi Parent 1",
        location_id=location.id,
        breed_id=breed.id,
        gender="Male",
        is_puppy=False
    )
    parent2 = Pet(
        user_id=test_user.id,
        name="Multi Parent 2",
        location_id=location.id,
        breed_id=breed.id,
        gender="Female",
        is_puppy=False
    )
    async_session.add_all([parent1, parent2])
    await async_session.commit()
    await async_session.refresh(parent1)
    await async_session.refresh(parent2)
    
    # Step 1: Create first breeding
    litter1_data = {"description": "First Multi-Breeding"}
    response1 = await async_client.post("/api/breedings/", json=litter1_data)
    assert response1.status_code == 201
    litter1_id = response1.json()["id"]
    
    # Step 2: Create second breeding
    litter2_data = {"description": "Second Multi-Breeding"}
    response2 = await async_client.post("/api/breedings/", json=litter2_data)
    assert response2.status_code == 201
    litter2_id = response2.json()["id"]
    
    # Step 3: Assign same pets to first breeding
    assign_data = {"pet_ids": [str(parent1.id), str(parent2.id)]}
    assign1_response = await async_client.post(
        f"/api/breedings/{litter1_id}/assign-pets",
        json=assign_data
    )
    assert assign1_response.status_code == 200
    litter1_with_pets = assign1_response.json()
    assert len(litter1_with_pets["parent_pets"]) == 2
    
    # Step 4: Assign same pets to second breeding
    assign2_response = await async_client.post(
        f"/api/breedings/{litter2_id}/assign-pets",
        json=assign_data
    )
    assert assign2_response.status_code == 200
    litter2_with_pets = assign2_response.json()
    assert len(litter2_with_pets["parent_pets"]) == 2
    
    # Step 5: Verify both breedings have the same parent pets
    get1_response = await async_client.get(f"/api/breedings/{litter1_id}")
    assert get1_response.status_code == 200
    litter1_final = get1_response.json()
    
    get2_response = await async_client.get(f"/api/breedings/{litter2_id}")
    assert get2_response.status_code == 200
    litter2_final = get2_response.json()
    
    # Both breedings should have the same parent pet IDs
    litter1_pet_ids = {p["id"] for p in litter1_final["parent_pets"]}
    litter2_pet_ids = {p["id"] for p in litter2_final["parent_pets"]}
    assert litter1_pet_ids == litter2_pet_ids
    assert str(parent1.id) in litter1_pet_ids
    assert str(parent2.id) in litter1_pet_ids
    
    # Step 6: Verify pets can be in multiple breedings (check database)
    from sqlalchemy import select
    from app.models.breeding_pet import BreedingPet
    
    query = select(BreedingPet).where(BreedingPet.pet_id == parent1.id)
    result = await async_session.execute(query)
    breeding_pets = result.scalars().all()
    
    # Parent1 should be in 2 breedings
    assert len(breeding_pets) == 2
    litter_ids_for_parent1 = {lp.breeding_id for lp in breeding_pets}
    assert litter1_id in litter_ids_for_parent1
    assert litter2_id in litter_ids_for_parent1


@pytest.mark.asyncio
async def test_location_mismatch_error_handling(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Test error handling when attempting to assign pets from different locations.
    
    This test verifies:
    1. Create two pets at different locations
    2. Create a breeding
    3. Attempt to assign pets from different locations
    4. Verify error is returned
    5. Verify breeding status remains unchanged
    
    Requirements: 3.1
    """
    from app.models.location import Location
    from app.models.breed import Breed
    from app.models.pet import Pet
    
    # Setup: Create two different locations
    location1 = Location(
        user_id=test_user.id,
        name="Location A",
        address1="111 A St",
        city="City A",
        state="State A",
        country="Country A",
        zipcode="11111",
        location_type="pet"
    )
    location2 = Location(
        user_id=test_user.id,
        name="Location B",
        address1="222 B St",
        city="City B",
        state="State B",
        country="Country B",
        zipcode="22222",
        location_type="pet"
    )
    async_session.add_all([location1, location2])
    await async_session.commit()
    await async_session.refresh(location1)
    await async_session.refresh(location2)
    
    breed = Breed(name="Error Test Breed", code="ETB")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Create pets at different locations
    pet_location1 = Pet(
        user_id=test_user.id,
        name="Pet at Location A",
        location_id=location1.id,
        breed_id=breed.id,
        gender="Male",
        is_puppy=False
    )
    pet_location2 = Pet(
        user_id=test_user.id,
        name="Pet at Location B",
        location_id=location2.id,
        breed_id=breed.id,
        gender="Female",
        is_puppy=False
    )
    async_session.add_all([pet_location1, pet_location2])
    await async_session.commit()
    await async_session.refresh(pet_location1)
    await async_session.refresh(pet_location2)
    
    # Step 1: Create a breeding
    breeding_data = {"description": "Error Test Breeding"}
    create_response = await async_client.post("/api/breedings/", json=breeding_data)
    assert create_response.status_code == 201
    breeding_id = create_response.json()["id"]
    
    # Step 2: Attempt to assign pets from different locations
    assign_data = {"pet_ids": [str(pet_location1.id), str(pet_location2.id)]}
    assign_response = await async_client.post(
        f"/api/breedings/{breeding_id}/assign-pets",
        json=assign_data
    )
    
    # Step 3: Verify error is returned
    assert assign_response.status_code == 400
    error_data = assign_response.json()
    assert "detail" in error_data
    assert "location" in error_data["detail"].lower()
    
    # Step 4: Verify breeding status remains unchanged
    get_response = await async_client.get(f"/api/breedings/{breeding_id}")
    assert get_response.status_code == 200
    breeding = get_response.json()
    
    assert breeding["status"] == "Started", "Status should remain 'Started' after failed assignment"
    assert breeding["parent_pets"] is None, "No pets should be assigned after failed assignment"


@pytest.mark.asyncio
async def test_complete_litter_with_void_workflow(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Test complete breeding workflow including voiding.
    
    This test verifies:
    1. Create breeding
    2. Assign pets
    3. Add puppies
    4. Void the breeding
    5. Verify breeding is voided but data is maintained
    6. Verify voided breeding is excluded from default listings
    
    Requirements: 1.1, 2.1, 2.2, 2.3, 4.1, 5.1, 6.1, 9.1, 9.2, 9.3, 9.4
    """
    from app.models.location import Location
    from app.models.breed import Breed
    from app.models.pet import Pet
    
    # Setup
    location = Location(
        user_id=test_user.id,
        name="Void Test Location",
        address1="999 Void St",
        city="Void City",
        state="Void State",
        country="Void Country",
        zipcode="99999",
        location_type="pet"
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    breed = Breed(name="Void Test Breed", code="VTB")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    parent1 = Pet(
        user_id=test_user.id,
        name="Void Parent 1",
        location_id=location.id,
        breed_id=breed.id,
        gender="Male",
        is_puppy=False
    )
    parent2 = Pet(
        user_id=test_user.id,
        name="Void Parent 2",
        location_id=location.id,
        breed_id=breed.id,
        gender="Female",
        is_puppy=False
    )
    async_session.add_all([parent1, parent2])
    await async_session.commit()
    await async_session.refresh(parent1)
    await async_session.refresh(parent2)
    
    # Step 1: Create breeding
    breeding_data = {"description": "Breeding to be voided"}
    create_response = await async_client.post("/api/breedings/", json=breeding_data)
    assert create_response.status_code == 201
    breeding_id = create_response.json()["id"]
    
    # Step 2: Assign pets
    assign_data = {"pet_ids": [str(parent1.id), str(parent2.id)]}
    assign_response = await async_client.post(
        f"/api/breedings/{breeding_id}/assign-pets",
        json=assign_data
    )
    assert assign_response.status_code == 200
    
    # Step 3: Add puppies
    puppies_data = {
        "puppies": [
            {
                "name": "Void Puppy 1",
                "gender": "Male",
                "birth_date": str(date.today()),
                "microchip": "VOID001"
            }
        ]
    }
    puppies_response = await async_client.post(
        f"/api/breedings/{breeding_id}/add-puppies",
        json=puppies_data
    )
    assert puppies_response.status_code == 200
    
    # Step 4: Void the breeding
    void_response = await async_client.delete(f"/api/breedings/{breeding_id}")
    assert void_response.status_code == 200
    voided_litter = void_response.json()
    
    # Verify status is Voided
    assert voided_litter["status"] == "Voided"
    
    # Step 5: Verify breeding data is maintained
    get_response = await async_client.get(f"/api/breedings/{breeding_id}")
    assert get_response.status_code == 200
    breeding = get_response.json()
    
    assert breeding["id"] == breeding_id
    assert breeding["description"] == "Breeding to be voided"
    assert breeding["status"] == "Voided"
    assert len(breeding["parent_pets"]) == 2
    assert len(breeding["puppies"]) == 1
    
    # Step 6: Verify voided breeding is excluded from default listings
    list_response = await async_client.get("/api/breedings/")
    assert list_response.status_code == 200
    breedings = list_response.json()
    
    litter_ids = [l["id"] for l in breedings]
    assert breeding_id not in litter_ids, "Voided breeding should be excluded from default listing"
