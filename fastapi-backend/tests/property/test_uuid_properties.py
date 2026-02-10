"""Property-based tests for UUID generation in models."""
import uuid
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Pet, Breed, Breeding, Location


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=st.emails(),
    name=st.text(min_size=1, max_size=255).filter(lambda x: x.strip() and '\x00' not in x),
)
async def test_property_user_uuid_generation(
    email: str,
    name: str,
    async_session: AsyncSession
):
    """
    Property 8: UUID Primary Key Generation - User
    
    For any created User entity, the generated ID should be a valid UUID v4.
    
    Feature: laravel-to-fastapi-migration, Property 8: UUID Primary Key Generation
    Validates: Requirements 4.3, 11.3
    """
    # Create user with generated UUID
    user = User(
        email=email,
        hashed_password="hashed_password_placeholder",
        name=name,
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    
    async_session.add(user)
    await async_session.flush()
    
    # Verify UUID is valid and version 4
    assert isinstance(user.id, uuid.UUID)
    assert user.id.version == 4
    
    await async_session.rollback()


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    pet_name=st.text(min_size=1, max_size=255).filter(lambda x: x.strip() and '\x00' not in x),
)
async def test_property_pet_uuid_generation(
    pet_name: str,
    async_session: AsyncSession
):
    """
    Property 8: UUID Primary Key Generation - Pet
    
    For any created Pet entity, the generated ID should be a valid UUID v4.
    
    Feature: laravel-to-fastapi-migration, Property 8: UUID Primary Key Generation
    Validates: Requirements 5.2, 11.3
    """
    # Create test user first
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_placeholder",
        name="Test User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(user)
    await async_session.flush()
    
    # Create pet with generated UUID
    pet = Pet(
        name=pet_name,
        user_id=user.id,
        is_deleted=False
    )
    
    async_session.add(pet)
    await async_session.flush()
    
    # Verify UUID is valid and version 4
    assert isinstance(pet.id, uuid.UUID)
    assert pet.id.version == 4
    
    await async_session.rollback()


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    breed_name=st.text(min_size=1, max_size=255).filter(lambda x: x.strip() and '\x00' not in x),
)
async def test_property_breed_id_generation(
    breed_name: str,
    async_session: AsyncSession
):
    """
    Property 8: UUID Primary Key Generation - Breed (Integer ID)
    
    For any created Breed entity, the generated ID should be a valid integer.
    Note: Breeds use integer IDs, not UUIDs, to match Laravel schema.
    
    Feature: laravel-to-fastapi-migration, Property 8: UUID Primary Key Generation
    Validates: Requirements 6.2, 11.3
    """
    # Create breed with auto-generated integer ID
    breed = Breed(
        name=breed_name,
        code=None,
        group=None
    )
    
    async_session.add(breed)
    await async_session.flush()
    
    # Verify ID is a valid integer
    assert isinstance(breed.id, int)
    assert breed.id > 0
    
    await async_session.rollback()


@pytest.mark.asyncio
async def test_property_litter_id_generation(
    async_session: AsyncSession
):
    """
    Property 8: UUID Primary Key Generation - Breeding (Integer ID)
    
    For any created Breeding entity, the generated ID should be a valid integer.
    Note: Litters use integer IDs, not UUIDs, to match Laravel schema.
    
    Feature: laravel-to-fastapi-migration, Property 8: UUID Primary Key Generation
    Validates: Requirements 7.2, 11.3
    """
    from datetime import date
    
    # Create breeding with auto-generated integer ID
    breeding = Breeding(
        date_of_litter=date.today(),
        is_active=True
    )
    
    async_session.add(breeding)
    await async_session.flush()
    
    # Verify ID is a valid integer
    assert isinstance(breeding.id, int)
    assert breeding.id > 0
    
    await async_session.rollback()


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    location_name=st.text(min_size=1, max_size=255).filter(lambda x: x.strip() and '\x00' not in x),
    city=st.text(min_size=1, max_size=255).filter(lambda x: x.strip() and '\x00' not in x),
)
async def test_property_location_id_generation(
    location_name: str,
    city: str,
    async_session: AsyncSession
):
    """
    Property 8: UUID Primary Key Generation - Location (Integer ID)
    
    For any created Location entity, the generated ID should be a valid integer.
    Note: Locations use integer IDs, not UUIDs, to match Laravel schema.
    
    Feature: laravel-to-fastapi-migration, Property 8: UUID Primary Key Generation
    Validates: Requirements 8.2, 11.3
    """
    # Create test user first
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_placeholder",
        name="Test User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(user)
    await async_session.flush()
    
    # Create location with auto-generated integer ID
    location = Location(
        name=location_name,
        address1="123 Main St",
        city=city,
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user",
        user_id=user.id
    )
    
    async_session.add(location)
    await async_session.flush()
    
    # Verify ID is a valid integer
    assert isinstance(location.id, int)
    assert location.id > 0
    
    await async_session.rollback()



@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_users=st.integers(min_value=2, max_value=10),
)
async def test_property_unique_uuid_assignment_users(
    num_users: int,
    async_session: AsyncSession
):
    """
    Property 9: Unique UUID Assignment - Users
    
    For any two entities created in the system, they should have different UUID values.
    This test creates multiple users and verifies all have unique UUIDs.
    
    Feature: laravel-to-fastapi-migration, Property 9: Unique UUID Assignment
    Validates: Requirements 4.5
    """
    users = []
    
    # Create multiple users
    for i in range(num_users):
        user = User(
            email=f"test{i}@example.com",
            hashed_password="hashed_password_placeholder",
            name=f"Test User {i}",
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        async_session.add(user)
        users.append(user)
    
    await async_session.flush()
    
    # Extract all UUIDs
    uuids = [user.id for user in users]
    
    # Verify all UUIDs are unique
    assert len(uuids) == len(set(uuids)), "All user UUIDs should be unique"
    
    # Verify no UUID is None
    assert all(uuid is not None for uuid in uuids), "No UUID should be None"
    
    await async_session.rollback()


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_pets=st.integers(min_value=2, max_value=10),
)
async def test_property_unique_uuid_assignment_pets(
    num_pets: int,
    async_session: AsyncSession
):
    """
    Property 9: Unique UUID Assignment - Pets
    
    For any two Pet entities created in the system, they should have different UUID values.
    This test creates multiple pets and verifies all have unique UUIDs.
    
    Feature: laravel-to-fastapi-migration, Property 9: Unique UUID Assignment
    Validates: Requirements 4.5
    """
    # Create test user first
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_placeholder",
        name="Test User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(user)
    await async_session.flush()
    
    pets = []
    
    # Create multiple pets
    for i in range(num_pets):
        pet = Pet(
            name=f"Pet {i}",
            user_id=user.id,
            is_deleted=False
        )
        async_session.add(pet)
        pets.append(pet)
    
    await async_session.flush()
    
    # Extract all UUIDs
    uuids = [pet.id for pet in pets]
    
    # Verify all UUIDs are unique
    assert len(uuids) == len(set(uuids)), "All pet UUIDs should be unique"
    
    # Verify no UUID is None
    assert all(uuid is not None for uuid in uuids), "No UUID should be None"
    
    await async_session.rollback()


@pytest.mark.asyncio
async def test_property_unique_uuid_assignment_mixed_entities(
    async_session: AsyncSession
):
    """
    Property 9: Unique UUID Assignment - Mixed Entities
    
    For any entities created in the system (users and pets), they should have different UUID values.
    This test creates both users and pets and verifies all UUIDs are unique across entity types.
    
    Feature: laravel-to-fastapi-migration, Property 9: Unique UUID Assignment
    Validates: Requirements 4.5
    """
    # Create users
    user1 = User(
        email="user1@example.com",
        hashed_password="hashed_password_placeholder",
        name="User 1",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    user2 = User(
        email="user2@example.com",
        hashed_password="hashed_password_placeholder",
        name="User 2",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    
    async_session.add(user1)
    async_session.add(user2)
    await async_session.flush()
    
    # Create pets
    pet1 = Pet(
        name="Pet 1",
        user_id=user1.id,
        is_deleted=False
    )
    pet2 = Pet(
        name="Pet 2",
        user_id=user2.id,
        is_deleted=False
    )
    
    async_session.add(pet1)
    async_session.add(pet2)
    await async_session.flush()
    
    # Extract all UUIDs
    all_uuids = [user1.id, user2.id, pet1.id, pet2.id]
    
    # Verify all UUIDs are unique (even across different entity types)
    assert len(all_uuids) == len(set(all_uuids)), "All UUIDs should be unique across entity types"
    
    # Verify no UUID is None
    assert all(uuid is not None for uuid in all_uuids), "No UUID should be None"
    
    await async_session.rollback()
