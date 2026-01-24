"""Unit tests for pet CRUD operations."""

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pet import Pet
from app.models.user import User
from app.models.breed import Breed


@pytest.fixture
async def test_breed(async_session: AsyncSession) -> Breed:
    """Create a test breed."""
    breed = Breed(
        name="Labrador Retriever",
        group="Sporting"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    return breed


@pytest.mark.asyncio
async def test_create_pet_with_valid_data(async_session: AsyncSession, test_user: User, test_breed: Breed):
    """Test creating a pet with all valid fields."""
    pet = Pet(
        user_id=test_user.id,
        name="Buddy",
        breed_id=test_breed.id,
        microchip="123456789",
        vaccination="Rabies, Distemper",
        health_certificate="HC-2024-001",
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    assert pet.id is not None
    assert isinstance(pet.id, uuid.UUID)
    assert pet.name == "Buddy"
    assert pet.user_id == test_user.id
    assert pet.breed_id == test_breed.id
    assert pet.microchip == "123456789"
    assert pet.is_deleted is False


@pytest.mark.asyncio
async def test_create_pet_minimal_data(async_session: AsyncSession, test_user: User):
    """Test creating a pet with only required fields."""
    pet = Pet(
        user_id=test_user.id,
        name="Max"
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    assert pet.id is not None
    assert pet.name == "Max"
    assert pet.user_id == test_user.id
    assert pet.breed_id is None
    assert pet.is_deleted is False


@pytest.mark.asyncio
async def test_update_pet(async_session: AsyncSession, test_user: User):
    """Test updating a pet's information."""
    # Create pet
    pet = Pet(
        user_id=test_user.id,
        name="Original Name",
        microchip="111111111"
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Update pet
    pet.name = "Updated Name"
    pet.microchip = "999999999"
    pet.vaccination = "Updated vaccination"
    
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify updates
    assert pet.name == "Updated Name"
    assert pet.microchip == "999999999"
    assert pet.vaccination == "Updated vaccination"


@pytest.mark.asyncio
async def test_soft_delete_pet(async_session: AsyncSession, test_user: User):
    """Test soft deletion of a pet."""
    # Create pet
    pet = Pet(
        user_id=test_user.id,
        name="To Be Deleted"
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    pet_id = pet.id
    
    # Soft delete
    pet.is_deleted = True
    await async_session.commit()
    
    # Verify pet still exists in database
    query = select(Pet).where(Pet.id == pet_id)
    result = await async_session.execute(query)
    deleted_pet = result.scalar_one_or_none()
    
    assert deleted_pet is not None
    assert deleted_pet.is_deleted is True
    assert deleted_pet.name == "To Be Deleted"


@pytest.mark.asyncio
async def test_query_pets_by_breeder(async_session: AsyncSession, test_user: User):
    """Test querying pets by breeder (user_id)."""
    # Create another user
    other_user = User(
        email="other@example.com",
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
    pet1 = Pet(user_id=test_user.id, name="Pet 1")
    pet2 = Pet(user_id=test_user.id, name="Pet 2")
    pet3 = Pet(user_id=test_user.id, name="Pet 3")
    
    # Create pet for other_user
    pet4 = Pet(user_id=other_user.id, name="Pet 4")
    
    async_session.add_all([pet1, pet2, pet3, pet4])
    await async_session.commit()
    
    # Query pets for test_user
    query = select(Pet).where(Pet.user_id == test_user.id)
    result = await async_session.execute(query)
    user_pets = result.scalars().all()
    
    assert len(user_pets) == 3
    assert all(pet.user_id == test_user.id for pet in user_pets)
    assert {pet.name for pet in user_pets} == {"Pet 1", "Pet 2", "Pet 3"}


@pytest.mark.asyncio
async def test_query_pets_exclude_deleted(async_session: AsyncSession, test_user: User):
    """Test querying pets excludes soft-deleted pets."""
    # Create pets
    pet1 = Pet(user_id=test_user.id, name="Active Pet", is_deleted=False)
    pet2 = Pet(user_id=test_user.id, name="Deleted Pet", is_deleted=True)
    
    async_session.add_all([pet1, pet2])
    await async_session.commit()
    
    # Query only active pets
    query = select(Pet).where(Pet.user_id == test_user.id, Pet.is_deleted == False)
    result = await async_session.execute(query)
    active_pets = result.scalars().all()
    
    assert len(active_pets) == 1
    assert active_pets[0].name == "Active Pet"


@pytest.mark.asyncio
async def test_pet_with_breed_relationship(async_session: AsyncSession, test_user: User, test_breed: Breed):
    """Test pet with breed relationship."""
    pet = Pet(
        user_id=test_user.id,
        name="Breed Test Pet",
        breed_id=test_breed.id
    )
    
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Access breed relationship
    assert pet.breed is not None
    assert pet.breed.name == "Labrador Retriever"
    assert pet.breed.group == "Sporting"


@pytest.mark.asyncio
async def test_update_pet_partial_fields(async_session: AsyncSession, test_user: User):
    """Test updating only specific fields of a pet."""
    # Create pet with multiple fields
    pet = Pet(
        user_id=test_user.id,
        name="Original",
        microchip="111",
        vaccination="Original Vax",
        health_certificate="Original HC"
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Update only name
    pet.name = "Updated"
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify only name changed
    assert pet.name == "Updated"
    assert pet.microchip == "111"
    assert pet.vaccination == "Original Vax"
    assert pet.health_certificate == "Original HC"
