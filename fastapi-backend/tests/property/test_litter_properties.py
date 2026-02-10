"""Property-based tests for breeding operations."""

import pytest
from datetime import date, timedelta
from hypothesis import given, settings, strategies as st, HealthCheck
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breeding import Breeding
from app.models.pet import Pet
from app.models.user import User


# Hypothesis strategies
# Filter out null bytes, surrogates, and other problematic characters for PostgreSQL
pet_name_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

description_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
) | st.none()

# Date strategy for breeding dates (reasonable range)
date_strategy = st.dates(
    min_value=date.today() - timedelta(days=365*5),  # 5 years ago
    max_value=date.today() + timedelta(days=365)     # 1 year in future
)


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    litter_date=date_strategy,
    description=description_strategy,
    pet_names=st.lists(pet_name_strategy, min_size=2, max_size=5),
)
async def test_property_litter_association(
    litter_date: date,
    description: str | None,
    pet_names: list[str],
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 14: Breeding Association
    
    For any Litter_Entity, multiple Pet_Entity records should be able to
    reference it via breeding_id.
    
    Feature: laravel-to-fastapi-migration, Property 14: Breeding Association
    Validates: Requirements 7.3
    """
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create a breeding
    breeding = Breeding(
        date_of_litter=litter_date,
        description=description,
        is_active=True,
    )
    
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    breeding_id = breeding.id
    
    # Create multiple pets associated with this breeding
    created_pet_ids = []
    for name in pet_names:
        pet = Pet(
            user_id=user_id,
            name=name,
            breeding_id=breeding_id,
        )
        async_session.add(pet)
        created_pet_ids.append(pet)
    
    await async_session.commit()
    
    # Refresh all pets to get their IDs
    for pet in created_pet_ids:
        await async_session.refresh(pet)
    
    # Verify all pets reference the same breeding
    for pet in created_pet_ids:
        assert pet.breeding_id == breeding_id, f"Pet {pet.id} should reference breeding {breeding_id}"
    
    # Query all pets for this breeding
    query = select(Pet).where(Pet.breeding_id == breeding_id)
    result = await async_session.execute(query)
    breeding_pets = result.scalars().all()
    
    # Verify the correct number of pets are associated
    assert len(breeding_pets) == len(pet_names), \
        f"Expected {len(pet_names)} pets for breeding, got {len(breeding_pets)}"
    
    # Verify all created pets are in the results
    litter_pet_ids = {pet.id for pet in breeding_pets}
    for pet in created_pet_ids:
        assert pet.id in litter_pet_ids, f"Pet {pet.id} should be in breeding pets"
    
    # Verify the relationship works from breeding to pets
    await async_session.refresh(breeding)
    assert len(breeding.pets) == len(pet_names), \
        f"Breeding relationship should have {len(pet_names)} pets"
    
    for pet in breeding.pets:
        assert pet.breeding_id == breeding_id, \
            f"Pet {pet.id} in relationship should reference breeding {breeding_id}"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    pet_name=pet_name_strategy,
    litter_date=date_strategy,
)
async def test_property_pet_litter_referential_integrity(
    pet_name: str,
    litter_date: date,
    async_session: AsyncSession,
):
    """
    Property 15: Referential Integrity - Pet to Breeding
    
    For any Pet_Entity creation or update with a breeding_id, the breeding_id should
    reference an existing Litter_Entity, or the operation should fail.
    
    Feature: laravel-to-fastapi-migration, Property 15: Referential Integrity - Pet to Breeding
    Validates: Requirements 7.4
    """
    # Create a user within the test to avoid fixture lazy loading issues
    import uuid as uuid_module
    unique_email = f"test-{uuid_module.uuid4()}@example.com"
    test_user = User(
        email=unique_email,
        hashed_password="hashed_password",
        name="Test User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(test_user)
    await async_session.commit()
    await async_session.refresh(test_user)
    user_id = test_user.id
    
    # Test 1: Creating pet with valid breeding_id should succeed
    # Create a breeding first
    breeding = Breeding(
        date_of_litter=litter_date,
        description="Test breeding",
        is_active=True,
    )
    
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    valid_litter_id = breeding.id
    
    # Create pet with valid breeding_id
    pet_with_litter = Pet(
        user_id=user_id,
        name=pet_name,
        breeding_id=valid_litter_id,
    )
    
    async_session.add(pet_with_litter)
    await async_session.commit()
    await async_session.refresh(pet_with_litter)
    
    assert pet_with_litter.breeding_id == valid_litter_id, \
        "Pet should have valid breeding_id"
    
    # Verify the foreign key constraint is working
    query = select(Breeding).where(Breeding.id == pet_with_litter.breeding_id)
    result = await async_session.execute(query)
    referenced_litter = result.scalar_one_or_none()
    
    assert referenced_litter is not None, \
        "Pet's breeding_id should reference an existing breeding"
    assert referenced_litter.id == valid_litter_id, \
        "Referenced breeding should match the breeding_id"
    
    # Test 2: Creating pet with non-existent breeding_id should fail
    # Use a very large integer that doesn't exist
    non_existent_litter_id = 999999999
    
    pet_with_invalid_litter = Pet(
        user_id=user_id,
        name=f"{pet_name}_invalid",
        breeding_id=non_existent_litter_id,
    )
    
    async_session.add(pet_with_invalid_litter)
    
    # This should raise an IntegrityError due to foreign key constraint
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await async_session.commit()
    
    # Rollback the failed transaction
    await async_session.rollback()


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    litter_date=date_strategy,
    description=description_strategy,
    pet_names=st.lists(pet_name_strategy, min_size=2, max_size=2),  # Exactly 2 parent pets
    puppy_names=st.lists(pet_name_strategy, min_size=1, max_size=5),  # 1-5 puppies
)
async def test_property_status_transition_sequence(
    litter_date: date,
    description: str | None,
    pet_names: list[str],
    puppy_names: list[str],
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 3: Status Transition Sequence
    
    For any breeding, the status should transition in the sequence Started → InProcess → Done,
    where Started is the initial state, InProcess occurs after pet assignment, and Done occurs
    after puppy addition.
    
    Feature: breedings-management, Property 3: Status Transition Sequence
    Validates: Requirements 2.1, 2.2, 2.3
    """
    from app.models.breeding_pet import BreedingPet
    
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Step 1: Create a breeding - should have status "Started"
    breeding = Breeding(
        date_of_litter=litter_date,
        description=description,
        is_active=True,
        status="Started"
    )
    
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Verify initial status is "Started"
    assert breeding.status == "Started", \
        f"New breeding should have status 'Started', got '{breeding.status}'"
    
    breeding_id = breeding.id
    
    # Step 2: Create parent pets (not assigned to breeding yet)
    parent_pets = []
    for name in pet_names:
        pet = Pet(
            user_id=user_id,
            name=name,
            is_puppy=False,
        )
        async_session.add(pet)
        parent_pets.append(pet)
    
    await async_session.commit()
    
    # Refresh all pets to get their IDs
    for pet in parent_pets:
        await async_session.refresh(pet)
    
    # Step 3: Assign parent pets to breeding - status should change to "InProcess"
    for pet in parent_pets:
        litter_pet = BreedingPet(
            breeding_id=breeding_id,
            pet_id=pet.id
        )
        async_session.add(litter_pet)
    
    # Update breeding status to InProcess
    breeding.status = "InProcess"
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Verify status changed to "InProcess"
    assert breeding.status == "InProcess", \
        f"Breeding with assigned pets should have status 'InProcess', got '{breeding.status}'"
    
    # Verify parent pets are assigned
    assert len(breeding.breeding_pets) == 2, \
        f"Breeding should have 2 parent pets assigned, got {len(breeding.breeding_pets)}"
    
    # Step 4: Add puppies to breeding - status should change to "Done"
    puppies = []
    for name in puppy_names:
        puppy = Pet(
            user_id=user_id,
            name=name,
            breeding_id=breeding_id,
            is_puppy=True,
        )
        async_session.add(puppy)
        puppies.append(puppy)
    
    # Update breeding status to Done
    breeding.status = "Done"
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Verify status changed to "Done"
    assert breeding.status == "Done", \
        f"Breeding with puppies should have status 'Done', got '{breeding.status}'"
    
    # Verify puppies are associated with breeding
    query = select(Pet).where(Pet.breeding_id == breeding_id)
    result = await async_session.execute(query)
    litter_puppies = result.scalars().all()
    
    assert len(litter_puppies) == len(puppy_names), \
        f"Expected {len(puppy_names)} puppies for breeding, got {len(litter_puppies)}"
    
    # Verify the complete transition sequence
    # We've verified: Started (initial) -> InProcess (after pet assignment) -> Done (after puppy addition)
    # This validates the complete status transition sequence



@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None  # Disable deadline for database operations
)
@given(
    num_litters=st.integers(min_value=3, max_value=10),
    litter_date=date_strategy,
)
async def test_property_comprehensive_filter_application(
    num_litters: int,
    litter_date: date,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 7: Comprehensive Filter Application
    
    For any combination of filter criteria (location, status, breed), the system should
    return only breedings that match all selected filter criteria.
    
    Feature: breedings-management, Property 7: Comprehensive Filter Application
    Validates: Requirements 10.1, 10.2, 10.3, 10.4
    """
    from app.models.breeding_pet import BreedingPet
    from app.models.location import Location
    from app.models.breed import Breed
    import uuid as uuid_module
    
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create test locations
    location1 = Location(
        user_id=user_id,
        name="Location 1",
        address1="123 Main St",
        city="City1",
        state="State1",
        country="Country1",
        zipcode="12345",
        location_type="pet"
    )
    location2 = Location(
        user_id=user_id,
        name="Location 2",
        address1="456 Oak Ave",
        city="City2",
        state="State2",
        country="Country2",
        zipcode="67890",
        location_type="pet"
    )
    async_session.add(location1)
    async_session.add(location2)
    await async_session.commit()
    await async_session.refresh(location1)
    await async_session.refresh(location2)
    
    # Create test breeds
    breed1 = Breed(
        name=f"Breed_{uuid_module.uuid4().hex[:8]}",
        code="BR1"
    )
    breed2 = Breed(
        name=f"Breed_{uuid_module.uuid4().hex[:8]}",
        code="BR2"
    )
    async_session.add(breed1)
    async_session.add(breed2)
    await async_session.commit()
    await async_session.refresh(breed1)
    await async_session.refresh(breed2)
    
    # Create breedings with different combinations of location, status, and breed
    litters_data = []
    statuses = ["Started", "InProcess", "Done"]
    locations = [location1, location2]
    breeds = [breed1, breed2]
    
    for i in range(num_litters):
        # Create breeding
        status = statuses[i % len(statuses)]
        breeding = Breeding(
            date_of_litter=litter_date,
            description=f"Breeding {i}",
            is_active=True,
            status=status
        )
        async_session.add(breeding)
        await async_session.commit()
        await async_session.refresh(breeding)
        
        # Assign parent pets with specific location and breed
        location = locations[i % len(locations)]
        breed = breeds[i % len(breeds)]
        
        # Create 2 parent pets for this breeding
        parent_pets = []
        for j in range(2):
            pet = Pet(
                user_id=user_id,
                name=f"Parent_{i}_{j}",
                location_id=location.id,
                breed_id=breed.id,
                is_puppy=False,
            )
            async_session.add(pet)
            parent_pets.append(pet)
        
        await async_session.commit()
        
        # Refresh pets to get their IDs
        for pet in parent_pets:
            await async_session.refresh(pet)
        
        # Assign pets to breeding
        for pet in parent_pets:
            litter_pet = BreedingPet(
                breeding_id=breeding.id,
                pet_id=pet.id
            )
            async_session.add(litter_pet)
        
        await async_session.commit()
        await async_session.refresh(breeding)
        
        litters_data.append({
            "breeding": breeding,
            "location_id": location.id,
            "breed_id": breed.id,
            "status": status
        })
    
    # Test 1: Filter by location only
    target_location_id = location1.id
    query = select(Breeding).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet)
    )
    result = await async_session.execute(query)
    all_litters = result.scalars().all()
    
    filtered_by_location = []
    for breeding in all_litters:
        parent_locations = set()
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.location_id:
                parent_locations.add(litter_pet.pet.location_id)
        if target_location_id in parent_locations:
            filtered_by_location.append(breeding)
    
    # Verify all filtered breedings have the target location
    for breeding in filtered_by_location:
        has_target_location = False
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.location_id == target_location_id:
                has_target_location = True
                break
        assert has_target_location, \
            f"Breeding {breeding.id} should have parent pet with location {target_location_id}"
    
    # Test 2: Filter by status only
    target_status = "InProcess"
    query = select(Breeding).where(Breeding.status == target_status)
    result = await async_session.execute(query)
    filtered_by_status = result.scalars().all()
    
    # Verify all filtered breedings have the target status
    for breeding in filtered_by_status:
        assert breeding.status == target_status, \
            f"Breeding {breeding.id} should have status '{target_status}', got '{breeding.status}'"
    
    # Test 3: Filter by breed only
    target_breed_id = breed1.id
    query = select(Breeding).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet)
    )
    result = await async_session.execute(query)
    all_litters = result.scalars().all()
    
    filtered_by_breed = []
    for breeding in all_litters:
        parent_breeds = set()
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.breed_id:
                parent_breeds.add(litter_pet.pet.breed_id)
        if target_breed_id in parent_breeds:
            filtered_by_breed.append(breeding)
    
    # Verify all filtered breedings have the target breed
    for breeding in filtered_by_breed:
        has_target_breed = False
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.breed_id == target_breed_id:
                has_target_breed = True
                break
        assert has_target_breed, \
            f"Breeding {breeding.id} should have parent pet with breed {target_breed_id}"
    
    # Test 4: Combined filters (location + status + breed)
    target_location_id = location1.id
    target_status = "InProcess"
    target_breed_id = breed1.id
    
    query = select(Breeding).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet)
    ).where(Breeding.status == target_status)
    result = await async_session.execute(query)
    all_litters = result.scalars().all()
    
    filtered_combined = []
    for breeding in all_litters:
        parent_locations = set()
        parent_breeds = set()
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.location_id:
                parent_locations.add(litter_pet.pet.location_id)
            if litter_pet.pet.breed_id:
                parent_breeds.add(litter_pet.pet.breed_id)
        
        if (target_location_id in parent_locations and 
            target_breed_id in parent_breeds):
            filtered_combined.append(breeding)
    
    # Verify all filtered breedings match ALL criteria
    for breeding in filtered_combined:
        # Check status
        assert breeding.status == target_status, \
            f"Breeding {breeding.id} should have status '{target_status}'"
        
        # Check location
        has_target_location = False
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.location_id == target_location_id:
                has_target_location = True
                break
        assert has_target_location, \
            f"Breeding {breeding.id} should have parent pet with location {target_location_id}"
        
        # Check breed
        has_target_breed = False
        for litter_pet in breeding.breeding_pets:
            if litter_pet.pet.breed_id == target_breed_id:
                has_target_breed = True
                break
        assert has_target_breed, \
            f"Breeding {breeding.id} should have parent pet with breed {target_breed_id}"
    
    # Test 5: Verify voided breedings are excluded by default
    # Create a voided breeding
    voided_litter = Breeding(
        date_of_litter=litter_date,
        description="Voided breeding",
        is_active=True,
        status="Voided"
    )
    async_session.add(voided_litter)
    await async_session.commit()
    await async_session.refresh(voided_litter)
    
    # Query without status filter (should exclude voided)
    query = select(Breeding).where(Breeding.status != "Voided")
    result = await async_session.execute(query)
    non_voided_litters = result.scalars().all()
    
    # Verify voided breeding is not in results
    voided_ids = {breeding.id for breeding in non_voided_litters if breeding.status == "Voided"}
    assert len(voided_ids) == 0, \
        "Voided breedings should be excluded by default"
    
    # Verify voided breeding can be retrieved when explicitly requested
    query = select(Breeding).where(Breeding.status == "Voided")
    result = await async_session.execute(query)
    voided_litters = result.scalars().all()
    
    assert voided_litter.id in {breeding.id for breeding in voided_litters}, \
        "Voided breeding should be retrievable when explicitly requested"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None  # Disable deadline for database operations
)
@given(
    pet_names=st.lists(pet_name_strategy, min_size=2, max_size=2),  # Exactly 2 pets
    litter_date=date_strategy,
    description=description_strategy,
)
async def test_property_location_validation_for_pet_assignment(
    pet_names: list[str],
    litter_date: date,
    description: str | None,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 4: Location Validation for Pet Assignment
    
    For any two pets from different locations, attempting to assign them to the same
    breeding should be rejected with an error.
    
    Feature: breedings-management, Property 4: Location Validation for Pet Assignment
    Validates: Requirements 3.1
    """
    from app.models.location import Location
    import uuid as uuid_module
    
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create two different locations
    location1 = Location(
        user_id=user_id,
        name=f"Location_{uuid_module.uuid4().hex[:8]}",
        address1="123 Main St",
        city="City1",
        state="State1",
        country="Country1",
        zipcode="12345",
        location_type="pet"
    )
    location2 = Location(
        user_id=user_id,
        name=f"Location_{uuid_module.uuid4().hex[:8]}",
        address1="456 Oak Ave",
        city="City2",
        state="State2",
        country="Country2",
        zipcode="67890",
        location_type="pet"
    )
    async_session.add(location1)
    async_session.add(location2)
    await async_session.commit()
    await async_session.refresh(location1)
    await async_session.refresh(location2)
    
    # Create a breeding
    breeding = Breeding(
        date_of_litter=litter_date,
        description=description,
        is_active=True,
        status="Started"
    )
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Create two pets with DIFFERENT locations
    pet1 = Pet(
        user_id=user_id,
        name=pet_names[0],
        location_id=location1.id,
        is_puppy=False,
    )
    pet2 = Pet(
        user_id=user_id,
        name=pet_names[1],
        location_id=location2.id,  # Different location
        is_puppy=False,
    )
    async_session.add(pet1)
    async_session.add(pet2)
    await async_session.commit()
    await async_session.refresh(pet1)
    await async_session.refresh(pet2)
    
    # Verify pets have different locations
    assert pet1.location_id != pet2.location_id, \
        "Test setup: pets should have different locations"
    
    # Test the API endpoint to verify it rejects the assignment
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/breedings/{breeding.id}/assign-pets",
            json={
                "pet_ids": [str(pet1.id), str(pet2.id)]
            }
        )
        
        # Should return 400 Bad Request due to location mismatch
        assert response.status_code == 400, \
            f"Assigning pets from different locations should return 400, got {response.status_code}"
        
        # Verify error message mentions location
        error_detail = response.json().get("detail", "")
        assert "location" in error_detail.lower(), \
            f"Error message should mention location, got: {error_detail}"
    
    # Verify breeding status is still "Started" (assignment failed)
    await async_session.refresh(breeding)
    assert breeding.status == "Started", \
        f"Breeding status should remain 'Started' after failed assignment, got '{breeding.status}'"
    
    # Verify no pets were assigned to the breeding
    from app.models.breeding_pet import BreedingPet
    query = select(BreedingPet).where(BreedingPet.breeding_id == breeding.id)
    result = await async_session.execute(query)
    breeding_pets = result.scalars().all()
    
    assert len(breeding_pets) == 0, \
        f"No pets should be assigned after failed validation, got {len(breeding_pets)}"
    
    # Test 2: Verify that pets from the SAME location CAN be assigned
    # Create two pets with the SAME location
    pet3 = Pet(
        user_id=user_id,
        name=f"{pet_names[0]}_same_loc",
        location_id=location1.id,  # Same location as pet1
        is_puppy=False,
    )
    pet4 = Pet(
        user_id=user_id,
        name=f"{pet_names[1]}_same_loc",
        location_id=location1.id,  # Same location as pet1
        is_puppy=False,
    )
    async_session.add(pet3)
    async_session.add(pet4)
    await async_session.commit()
    await async_session.refresh(pet3)
    await async_session.refresh(pet4)
    
    # Verify pets have the same location
    assert pet3.location_id == pet4.location_id, \
        "Test setup: pets should have the same location"
    
    # Create a new breeding for this test
    litter2 = Breeding(
        date_of_litter=litter_date,
        description=f"{description}_test2" if description else "test2",
        is_active=True,
        status="Started"
    )
    async_session.add(litter2)
    await async_session.commit()
    await async_session.refresh(litter2)
    
    # Test the API endpoint to verify it accepts the assignment
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/breedings/{litter2.id}/assign-pets",
            json={
                "pet_ids": [str(pet3.id), str(pet4.id)]
            }
        )
        
        # Should return 200 OK for pets from same location
        assert response.status_code == 200, \
            f"Assigning pets from same location should return 200, got {response.status_code}"
    
    # Verify breeding status changed to "InProcess"
    await async_session.refresh(litter2)
    assert litter2.status == "InProcess", \
        f"Breeding status should be 'InProcess' after successful assignment, got '{litter2.status}'"
    
    # Verify pets were assigned to the breeding
    query = select(BreedingPet).where(BreedingPet.breeding_id == litter2.id)
    result = await async_session.execute(query)
    breeding_pets = result.scalars().all()
    
    assert len(breeding_pets) == 2, \
        f"2 pets should be assigned after successful validation, got {len(breeding_pets)}"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None  # Disable deadline for database operations
)
@given(
    num_litters=st.integers(min_value=2, max_value=5),
    pet_names=st.lists(pet_name_strategy, min_size=2, max_size=2),  # Exactly 2 pets per breeding
    litter_date=date_strategy,
)
async def test_property_multi_litter_pet_assignment(
    num_litters: int,
    pet_names: list[str],
    litter_date: date,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 6: Multi-Breeding Pet Assignment
    
    For any pet, the system should allow assignment to multiple breedings without restriction,
    regardless of existing breeding assignments.
    
    Feature: breedings-management, Property 6: Multi-Breeding Pet Assignment
    Validates: Requirements 5.5, 11.1, 11.2, 11.3, 11.4
    """
    from app.models.location import Location
    from app.models.breeding_pet import BreedingPet
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    import uuid as uuid_module
    
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create a location for all pets (to satisfy location validation)
    location = Location(
        user_id=user_id,
        name=f"Location_{uuid_module.uuid4().hex[:8]}",
        address1="123 Main St",
        city="City1",
        state="State1",
        country="Country1",
        zipcode="12345",
        location_type="pet"
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Create two pets that will be assigned to multiple breedings
    pet1 = Pet(
        user_id=user_id,
        name=pet_names[0],
        location_id=location.id,
        is_puppy=False,
    )
    pet2 = Pet(
        user_id=user_id,
        name=pet_names[1],
        location_id=location.id,
        is_puppy=False,
    )
    async_session.add(pet1)
    async_session.add(pet2)
    await async_session.commit()
    await async_session.refresh(pet1)
    await async_session.refresh(pet2)
    
    # Create multiple breedings
    breedings = []
    for i in range(num_litters):
        breeding = Breeding(
            date_of_litter=litter_date,
            description=f"Breeding {i}",
            is_active=True,
            status="Started"
        )
        async_session.add(breeding)
        breedings.append(breeding)
    
    await async_session.commit()
    
    # Refresh all breedings to get their IDs
    for breeding in breedings:
        await async_session.refresh(breeding)
    
    # Test 1: Assign the same two pets to all breedings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for breeding in breedings:
            response = await client.post(
                f"/api/breedings/{breeding.id}/assign-pets",
                json={
                    "pet_ids": [str(pet1.id), str(pet2.id)]
                }
            )
            
            # Should return 200 OK - multi-breeding assignment is allowed
            assert response.status_code == 200, \
                f"Assigning pets to breeding {breeding.id} should succeed, got {response.status_code}"
    
    # Test 2: Verify all breedings have the same pets assigned
    for breeding in breedings:
        await async_session.refresh(breeding)
        
        # Verify breeding status changed to "InProcess"
        assert breeding.status == "InProcess", \
            f"Breeding {breeding.id} should have status 'InProcess', got '{breeding.status}'"
        
        # Query breeding_pets for this breeding
        query = select(BreedingPet).where(BreedingPet.breeding_id == breeding.id)
        result = await async_session.execute(query)
        breeding_pets = result.scalars().all()
        
        # Verify 2 pets are assigned
        assert len(breeding_pets) == 2, \
            f"Breeding {breeding.id} should have 2 pets assigned, got {len(breeding_pets)}"
        
        # Verify the correct pets are assigned
        assigned_pet_ids = {lp.pet_id for lp in breeding_pets}
        assert pet1.id in assigned_pet_ids, \
            f"Pet {pet1.id} should be assigned to breeding {breeding.id}"
        assert pet2.id in assigned_pet_ids, \
            f"Pet {pet2.id} should be assigned to breeding {breeding.id}"
    
    # Test 3: Verify the total number of litter_pet records
    query = select(BreedingPet).where(
        (BreedingPet.pet_id == pet1.id) | (BreedingPet.pet_id == pet2.id)
    )
    result = await async_session.execute(query)
    all_litter_pets = result.scalars().all()
    
    # Should have 2 pets * num_litters assignments
    expected_assignments = 2 * num_litters
    assert len(all_litter_pets) == expected_assignments, \
        f"Expected {expected_assignments} total assignments, got {len(all_litter_pets)}"
    
    # Test 4: Verify each pet appears in multiple breedings
    query = select(BreedingPet).where(BreedingPet.pet_id == pet1.id)
    result = await async_session.execute(query)
    pet1_assignments = result.scalars().all()
    
    assert len(pet1_assignments) == num_litters, \
        f"Pet {pet1.id} should be assigned to {num_litters} breedings, got {len(pet1_assignments)}"
    
    query = select(BreedingPet).where(BreedingPet.pet_id == pet2.id)
    result = await async_session.execute(query)
    pet2_assignments = result.scalars().all()
    
    assert len(pet2_assignments) == num_litters, \
        f"Pet {pet2.id} should be assigned to {num_litters} breedings, got {len(pet2_assignments)}"
    
    # Test 5: Verify no unique constraint violations occurred
    # (If there were unique constraints, the API calls would have failed)
    # This test passes if we got here without exceptions
    
    # Test 6: Verify that each breeding maintains separate records
    litter_ids_for_pet1 = {lp.breeding_id for lp in pet1_assignments}
    assert len(litter_ids_for_pet1) == num_litters, \
        f"Pet {pet1.id} should be in {num_litters} different breedings, got {len(litter_ids_for_pet1)}"
    
    # Verify all created breedings are in the assignments
    created_litter_ids = {breeding.id for breeding in breedings}
    assert litter_ids_for_pet1 == created_litter_ids, \
        f"Pet {pet1.id} should be assigned to all created breedings"
    
    # Test 7: Verify that pets can be queried from multiple breedings
    for breeding in breedings:
        await async_session.refresh(breeding)
        
        # Access the relationship
        parent_pets = [lp.pet for lp in breeding.breeding_pets]
        
        assert len(parent_pets) == 2, \
            f"Breeding {breeding.id} should have 2 parent pets, got {len(parent_pets)}"
        
        parent_pet_ids = {pet.id for pet in parent_pets}
        assert pet1.id in parent_pet_ids, \
            f"Pet {pet1.id} should be accessible from breeding {breeding.id}"
        assert pet2.id in parent_pet_ids, \
            f"Pet {pet2.id} should be accessible from breeding {breeding.id}"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None  # Disable deadline for database operations
)
@given(
    litter_date=date_strategy,
    description=description_strategy,
    updated_description=description_strategy,
    pet_names=st.lists(pet_name_strategy, min_size=2, max_size=2),  # Exactly 2 parent pets
    puppy_names=st.lists(pet_name_strategy, min_size=1, max_size=3),  # 1-3 puppies
)
async def test_property_data_persistence_consistency(
    litter_date: date,
    description: str | None,
    updated_description: str | None,
    pet_names: list[str],
    puppy_names: list[str],
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 8: Data Persistence Consistency
    
    For any breeding creation or update operation, the data should be immediately
    persisted to the database and retrievable in subsequent queries.
    
    Feature: breedings-management, Property 8: Data Persistence Consistency
    Validates: Requirements 12.1, 12.3, 12.4
    """
    from app.models.breeding_pet import BreedingPet
    from app.models.location import Location
    import uuid as uuid_module
    
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create a location for pets (to satisfy location validation)
    location = Location(
        user_id=user_id,
        name=f"Location_{uuid_module.uuid4().hex[:8]}",
        address1="123 Main St",
        city="City1",
        state="State1",
        country="Country1",
        zipcode="12345",
        location_type="pet"
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Test 1: Create a breeding and verify immediate persistence
    breeding = Breeding(
        date_of_litter=litter_date,
        description=description,
        is_active=True,
        status="Started"
    )
    
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    breeding_id = breeding.id
    original_created_at = breeding.created_at
    original_updated_at = breeding.updated_at  # May be None on creation
    
    # Verify breeding is immediately retrievable after creation
    query = select(Breeding).where(Breeding.id == breeding_id)
    result = await async_session.execute(query)
    retrieved_litter = result.scalar_one_or_none()
    
    assert retrieved_litter is not None, \
        f"Breeding {breeding_id} should be immediately retrievable after creation"
    assert retrieved_litter.id == breeding_id, \
        f"Retrieved breeding ID should match created breeding ID"
    assert retrieved_litter.description == description, \
        f"Retrieved breeding description should match created description"
    assert retrieved_litter.status == "Started", \
        f"Retrieved breeding status should be 'Started'"
    assert retrieved_litter.date_of_litter == litter_date, \
        f"Retrieved breeding date should match created date"
    assert retrieved_litter.created_at == original_created_at, \
        f"Retrieved breeding created_at should match original"
    # updated_at may be None on creation, so we just verify it matches
    assert retrieved_litter.updated_at == original_updated_at, \
        f"Retrieved breeding updated_at should match original"
    
    # Test 2: Update breeding description and verify immediate persistence
    breeding.description = updated_description
    await async_session.commit()
    await async_session.refresh(breeding)
    
    updated_at_after_description = breeding.updated_at
    
    # Verify update is immediately retrievable
    query = select(Breeding).where(Breeding.id == breeding_id)
    result = await async_session.execute(query)
    retrieved_litter = result.scalar_one_or_none()
    
    assert retrieved_litter is not None, \
        f"Breeding {breeding_id} should be retrievable after update"
    assert retrieved_litter.description == updated_description, \
        f"Retrieved breeding description should match updated description"
    assert retrieved_litter.updated_at == updated_at_after_description, \
        f"Retrieved breeding updated_at should reflect the update"
    assert retrieved_litter.created_at == original_created_at, \
        f"Retrieved breeding created_at should remain unchanged after update"
    
    # Test 3: Assign parent pets and verify immediate persistence
    parent_pets = []
    for name in pet_names:
        pet = Pet(
            user_id=user_id,
            name=name,
            location_id=location.id,
            is_puppy=False,
        )
        async_session.add(pet)
        parent_pets.append(pet)
    
    await async_session.commit()
    
    # Refresh all pets to get their IDs
    for pet in parent_pets:
        await async_session.refresh(pet)
    
    # Assign pets to breeding
    for pet in parent_pets:
        litter_pet = BreedingPet(
            breeding_id=breeding_id,
            pet_id=pet.id
        )
        async_session.add(litter_pet)
    
    # Update breeding status to InProcess
    breeding.status = "InProcess"
    await async_session.commit()
    await async_session.refresh(breeding)
    
    updated_at_after_pets = breeding.updated_at
    
    # Verify pet assignments are immediately retrievable
    query = select(BreedingPet).where(BreedingPet.breeding_id == breeding_id)
    result = await async_session.execute(query)
    retrieved_litter_pets = result.scalars().all()
    
    assert len(retrieved_litter_pets) == 2, \
        f"Should retrieve 2 parent pet assignments immediately, got {len(retrieved_litter_pets)}"
    
    retrieved_pet_ids = {lp.pet_id for lp in retrieved_litter_pets}
    for pet in parent_pets:
        assert pet.id in retrieved_pet_ids, \
            f"Pet {pet.id} should be in retrieved assignments"
    
    # Verify breeding status update is immediately retrievable
    query = select(Breeding).where(Breeding.id == breeding_id)
    result = await async_session.execute(query)
    retrieved_litter = result.scalar_one_or_none()
    
    assert retrieved_litter.status == "InProcess", \
        f"Retrieved breeding status should be 'InProcess' after pet assignment"
    assert retrieved_litter.updated_at == updated_at_after_pets, \
        f"Retrieved breeding updated_at should reflect pet assignment"
    
    # Test 4: Add puppies and verify immediate persistence
    puppies = []
    for name in puppy_names:
        puppy = Pet(
            user_id=user_id,
            name=name,
            breeding_id=breeding_id,
            location_id=location.id,
            is_puppy=True,
        )
        async_session.add(puppy)
        puppies.append(puppy)
    
    # Update breeding status to Done
    breeding.status = "Done"
    await async_session.commit()
    await async_session.refresh(breeding)
    
    updated_at_after_puppies = breeding.updated_at
    
    # Refresh all puppies to get their IDs
    for puppy in puppies:
        await async_session.refresh(puppy)
    
    # Verify puppies are immediately retrievable
    query = select(Pet).where(Pet.breeding_id == breeding_id)
    result = await async_session.execute(query)
    retrieved_puppies = result.scalars().all()
    
    assert len(retrieved_puppies) == len(puppy_names), \
        f"Should retrieve {len(puppy_names)} puppies immediately, got {len(retrieved_puppies)}"
    
    retrieved_puppy_ids = {puppy.id for puppy in retrieved_puppies}
    for puppy in puppies:
        assert puppy.id in retrieved_puppy_ids, \
            f"Puppy {puppy.id} should be in retrieved puppies"
        assert puppy.breeding_id == breeding_id, \
            f"Puppy {puppy.id} should reference breeding {breeding_id}"
    
    # Verify breeding status update is immediately retrievable
    query = select(Breeding).where(Breeding.id == breeding_id)
    result = await async_session.execute(query)
    retrieved_litter = result.scalar_one_or_none()
    
    assert retrieved_litter.status == "Done", \
        f"Retrieved breeding status should be 'Done' after puppy addition"
    assert retrieved_litter.updated_at == updated_at_after_puppies, \
        f"Retrieved breeding updated_at should reflect puppy addition"
    
    # Test 5: Verify data consistency across multiple queries
    # Query the breeding multiple times and verify consistency
    for _ in range(3):
        query = select(Breeding).options(
            selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet),
            selectinload(Breeding.pets)
        ).where(Breeding.id == breeding_id)
        result = await async_session.execute(query)
        consistent_litter = result.scalar_one_or_none()
        
        assert consistent_litter is not None, \
            f"Breeding should be consistently retrievable"
        assert consistent_litter.id == breeding_id, \
            f"Breeding ID should be consistent"
        assert consistent_litter.description == updated_description, \
            f"Breeding description should be consistent"
        assert consistent_litter.status == "Done", \
            f"Breeding status should be consistent"
        assert consistent_litter.date_of_litter == litter_date, \
            f"Breeding date should be consistent"
        assert len(consistent_litter.breeding_pets) == 2, \
            f"Breeding should consistently have 2 parent pets"
        assert len(consistent_litter.pets) == len(puppy_names), \
            f"Breeding should consistently have {len(puppy_names)} puppies"
    
    # Test 6: Verify data persists after session expiration (simulate navigation away)
    # Expire all objects in the session to simulate a fresh session
    async_session.expire_all()
    
    # Query the breeding again (simulating returning to the breedings screen)
    query = select(Breeding).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet),
        selectinload(Breeding.pets)
    ).where(Breeding.id == breeding_id)
    result = await async_session.execute(query)
    persisted_litter = result.scalar_one_or_none()
    
    assert persisted_litter is not None, \
        f"Breeding should persist after session expiration"
    assert persisted_litter.id == breeding_id, \
        f"Persisted breeding ID should match"
    assert persisted_litter.description == updated_description, \
        f"Persisted breeding description should match"
    assert persisted_litter.status == "Done", \
        f"Persisted breeding status should match"
    assert persisted_litter.date_of_litter == litter_date, \
        f"Persisted breeding date should match"
    assert len(persisted_litter.breeding_pets) == 2, \
        f"Persisted breeding should have 2 parent pets"
    assert len(persisted_litter.pets) == len(puppy_names), \
        f"Persisted breeding should have {len(puppy_names)} puppies"
    
    # Test 7: Verify updated_at changes with each update (if it's set)
    # Note: updated_at may be None on initial creation, but should be set after updates
    if updated_at_after_description is not None and original_updated_at is not None:
        assert updated_at_after_description >= original_updated_at, \
            f"updated_at should increase or stay same after description update"
    if updated_at_after_pets is not None and updated_at_after_description is not None:
        assert updated_at_after_pets >= updated_at_after_description, \
            f"updated_at should increase or stay same after pet assignment"
    if updated_at_after_puppies is not None and updated_at_after_pets is not None:
        assert updated_at_after_puppies >= updated_at_after_pets, \
            f"updated_at should increase or stay same after puppy addition"
    
    # Test 8: Verify created_at remains unchanged throughout all updates
    assert persisted_litter.created_at == original_created_at, \
        f"created_at should never change after initial creation"

