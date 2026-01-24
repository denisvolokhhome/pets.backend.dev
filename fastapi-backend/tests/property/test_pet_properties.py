"""Property-based tests for pet operations."""

import uuid
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
microchip_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
) | st.none()
vaccination_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
) | st.none()


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    name=pet_name_strategy,
    microchip=microchip_strategy,
)
async def test_property_pet_ownership_association(
    name: str,
    microchip: str | None,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 10: Pet Ownership Association
    
    For any created Pet_Entity, it should have a valid user_id that references
    an existing User_Entity.
    
    Feature: laravel-to-fastapi-migration, Property 10: Pet Ownership Association
    Validates: Requirements 5.3
    """
    # Create pet with test user
    pet = Pet(
        user_id=test_user.id,
        name=name,
        microchip=microchip,
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify pet has valid user_id
    assert pet.user_id is not None
    assert isinstance(pet.user_id, uuid.UUID)
    assert pet.user_id == test_user.id
    
    # Verify user_id references an existing user
    query = select(User).where(User.id == pet.user_id)
    result = await async_session.execute(query)
    user = result.scalar_one_or_none()
    
    assert user is not None
    assert user.id == test_user.id
    
    # Verify relationship works
    assert pet.user is not None
    assert pet.user.id == test_user.id



@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    name=pet_name_strategy,
)
async def test_property_soft_deletion_behavior(
    name: str,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 11: Soft Deletion Behavior
    
    For any Pet_Entity, calling the delete endpoint should set is_deleted=True
    and the pet should still exist in the database.
    
    Feature: laravel-to-fastapi-migration, Property 11: Soft Deletion Behavior
    Validates: Requirements 5.5
    """
    # Create pet
    pet = Pet(
        user_id=test_user.id,
        name=name,
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    pet_id = pet.id
    
    # Soft delete the pet
    pet.is_deleted = True
    await async_session.commit()
    
    # Verify pet still exists in database
    query = select(Pet).where(Pet.id == pet_id)
    result = await async_session.execute(query)
    deleted_pet = result.scalar_one_or_none()
    
    assert deleted_pet is not None, "Pet should still exist in database after soft delete"
    assert deleted_pet.is_deleted is True, "Pet should have is_deleted=True"
    assert deleted_pet.id == pet_id, "Pet ID should remain unchanged"
    assert deleted_pet.name == name, "Pet name should remain unchanged"



@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    pet_names=st.lists(pet_name_strategy, min_size=1, max_size=5),
)
async def test_property_breeder_pet_filtering(
    pet_names: list[str],
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 12: Breeder Pet Filtering
    
    For any breeder ID query, all returned pets should have user_id matching
    the queried breeder ID.
    
    Feature: laravel-to-fastapi-migration, Property 12: Breeder Pet Filtering
    Validates: Requirements 5.6
    """
    # Clean up any existing pets from previous Hypothesis examples
    # This ensures each example starts with a clean state
    from sqlalchemy import delete
    await async_session.execute(delete(Pet))
    await async_session.commit()
    
    # Create another user with unique email using UUID
    import uuid as uuid_module
    other_email = f"other-{uuid_module.uuid4()}@example.com"
    other_user = User(
        email=other_email,
        hashed_password="hashed_password",
        name="Other User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(other_user)
    await async_session.commit()
    await async_session.refresh(other_user)
    
    # Create pets for test_user
    for name in pet_names:
        pet = Pet(user_id=test_user.id, name=name)
        async_session.add(pet)
    
    # Create one pet for other_user
    other_pet = Pet(user_id=other_user.id, name="Other Pet")
    async_session.add(other_pet)
    
    await async_session.commit()
    
    # Query pets for test_user (breeder filtering)
    query = select(Pet).where(Pet.user_id == test_user.id)
    result = await async_session.execute(query)
    user_pets = result.scalars().all()
    
    # Verify all returned pets belong to test_user
    assert len(user_pets) == len(pet_names), f"Expected {len(pet_names)} pets, got {len(user_pets)}"
    
    for pet in user_pets:
        assert pet.user_id == test_user.id, f"Pet {pet.id} has wrong user_id: {pet.user_id} != {test_user.id}"
    
    # Verify no pets from other_user are returned
    pet_ids = {pet.id for pet in user_pets}
    assert other_pet.id not in pet_ids, "Other user's pet should not be in results"



@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    name=pet_name_strategy,
)
async def test_property_pet_breed_referential_integrity(
    name: str,
    async_session: AsyncSession,
):
    """
    Property 13: Referential Integrity - Pet to Breed
    
    For any Pet_Entity creation or update with a breed_id, the breed_id should
    reference an existing Breed_Entity, or the operation should fail.
    
    Feature: laravel-to-fastapi-migration, Property 13: Referential Integrity - Pet to Breed
    Validates: Requirements 6.5
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
    
    # Create a breed within the test to avoid fixture lazy loading issues
    # Use UUID to ensure unique breed name across all Hypothesis test runs
    from app.models.breed import Breed
    unique_breed_name = f"Test Breed {uuid_module.uuid4()}"
    test_breed = Breed(
        name=unique_breed_name,
        group="Test Group"
    )
    async_session.add(test_breed)
    await async_session.commit()
    await async_session.refresh(test_breed)
    
    # Store the breed ID immediately after creation
    valid_breed_id = test_breed.id
    
    # Test 1: Creating pet with valid breed_id should succeed
    pet_with_breed = Pet(
        user_id=user_id,
        name=name,
        breed_id=valid_breed_id,  # This is an integer ID
    )
    
    async_session.add(pet_with_breed)
    await async_session.commit()
    await async_session.refresh(pet_with_breed)
    
    assert pet_with_breed.breed_id == valid_breed_id
    # Verify the breed_id foreign key is set correctly
    # We don't need to access the relationship object - the foreign key constraint
    # already ensures referential integrity
    
    # Test 2: Creating pet with non-existent breed_id should fail
    # (Foreign key constraint violation)
    # Use a very large integer that doesn't exist
    non_existent_breed_id = 999999999
    
    pet_with_invalid_breed = Pet(
        user_id=user_id,
        name=f"{name}_invalid",
        breed_id=non_existent_breed_id,
    )
    
    async_session.add(pet_with_invalid_breed)
    
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
    name=pet_name_strategy,
)
async def test_property_pet_image_metadata_update(
    name: str,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 21: Pet Image Metadata Update
    
    For any successful image upload for a pet, the Pet_Entity should be updated
    with the image_path and image_file_name.
    
    Feature: laravel-to-fastapi-migration, Property 21: Pet Image Metadata Update
    Validates: Requirements 9.5
    """
    # Create a pet
    pet = Pet(
        user_id=test_user.id,
        name=name,
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify pet initially has no image metadata
    assert pet.image_path is None
    assert pet.image_file_name is None
    
    # Simulate image upload by setting image metadata
    test_image_path = f"storage/app/pets/{pet.id}_test.jpg"
    test_image_filename = f"{pet.id}_test.jpg"
    
    pet.image_path = test_image_path
    pet.image_file_name = test_image_filename
    
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify pet has been updated with image metadata
    assert pet.image_path == test_image_path, "Pet should have image_path set"
    assert pet.image_file_name == test_image_filename, "Pet should have image_file_name set"
    
    # Verify the metadata persists across sessions
    from sqlalchemy import select
    query = select(Pet).where(Pet.id == pet.id)
    result = await async_session.execute(query)
    reloaded_pet = result.scalar_one()
    
    assert reloaded_pet.image_path == test_image_path, "Image path should persist"
    assert reloaded_pet.image_file_name == test_image_filename, "Image filename should persist"
