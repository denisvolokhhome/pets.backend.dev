"""Unit tests for model relationships."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Pet, Breed, Breeding, Location


@pytest.mark.asyncio
async def test_pet_user_relationship(async_session: AsyncSession, test_user: User):
    """
    Test Pet → User relationship.
    
    Verifies that a pet is correctly associated with its owner user.
    Validates: Requirements 11.4
    """
    # Create a pet associated with the test user
    pet = Pet(
        name="Test Pet",
        user_id=test_user.id,
        is_deleted=False
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify the relationship
    assert pet.user_id == test_user.id
    assert pet.user is not None
    assert pet.user.id == test_user.id
    assert pet.user.email == test_user.email
    
    # Verify reverse relationship
    await async_session.refresh(test_user)
    assert len(test_user.pets) > 0
    assert any(p.id == pet.id for p in test_user.pets)


@pytest.mark.asyncio
async def test_pet_breed_relationship(async_session: AsyncSession, test_user: User):
    """
    Test Pet → Breed relationship.
    
    Verifies that a pet is correctly associated with its breed.
    Validates: Requirements 11.4
    """
    # Create a breed
    breed = Breed(
        name="Test Breed",
        code="TB",
        group="Test Group"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Create a pet with the breed
    pet = Pet(
        name="Test Pet",
        user_id=test_user.id,
        breed_id=breed.id,
        is_deleted=False
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify the relationship
    assert pet.breed_id == breed.id
    assert pet.breed is not None
    assert pet.breed.id == breed.id
    assert pet.breed.name == "Test Breed"
    
    # Verify reverse relationship
    await async_session.refresh(breed)
    assert len(breed.pets) > 0
    assert any(p.id == pet.id for p in breed.pets)


@pytest.mark.asyncio
async def test_pet_litter_relationship(async_session: AsyncSession, test_user: User):
    """
    Test Pet → Breeding relationship.
    
    Verifies that a pet is correctly associated with its breeding.
    Validates: Requirements 11.4
    """
    from datetime import date
    
    # Create a breeding
    breeding = Breeding(
        date_of_litter=date.today(),
        description="Test Breeding",
        is_active=True
    )
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Create a pet with the breeding
    pet = Pet(
        name="Test Pet",
        user_id=test_user.id,
        breeding_id=breeding.id,
        is_deleted=False
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify the relationship
    assert pet.breeding_id == breeding.id
    assert pet.breeding is not None
    assert pet.breeding.id == breeding.id
    assert pet.breeding.date_of_litter == date.today()
    
    # Verify reverse relationship
    await async_session.refresh(breeding)
    assert len(breeding.pets) > 0
    assert any(p.id == pet.id for p in breeding.pets)


@pytest.mark.asyncio
async def test_location_user_relationship(async_session: AsyncSession, test_user: User):
    """
    Test Location → User relationship.
    
    Verifies that a location is correctly associated with its owner user.
    Validates: Requirements 11.4
    """
    # Create a location associated with the test user
    location = Location(
        name="Test Location",
        address1="123 Test St",
        city="Test City",
        state="TS",
        country="Test Country",
        zipcode="12345",
        location_type="user",
        user_id=test_user.id
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Verify the relationship
    assert location.user_id == test_user.id
    assert location.user is not None
    assert location.user.id == test_user.id
    assert location.user.email == test_user.email
    
    # Verify reverse relationship
    await async_session.refresh(test_user)
    assert len(test_user.locations) > 0
    assert any(loc.id == location.id for loc in test_user.locations)


@pytest.mark.asyncio
async def test_multiple_pets_same_user(async_session: AsyncSession, test_user: User):
    """
    Test that a user can have multiple pets.
    
    Verifies the one-to-many relationship between User and Pet.
    Validates: Requirements 11.4
    """
    # Create multiple pets for the same user
    pet1 = Pet(name="Pet 1", user_id=test_user.id, is_deleted=False)
    pet2 = Pet(name="Pet 2", user_id=test_user.id, is_deleted=False)
    pet3 = Pet(name="Pet 3", user_id=test_user.id, is_deleted=False)
    
    async_session.add_all([pet1, pet2, pet3])
    await async_session.commit()
    
    # Refresh user to load relationships
    await async_session.refresh(test_user)
    
    # Verify all pets are associated with the user
    assert len(test_user.pets) >= 3
    pet_names = {pet.name for pet in test_user.pets}
    assert "Pet 1" in pet_names
    assert "Pet 2" in pet_names
    assert "Pet 3" in pet_names


@pytest.mark.asyncio
async def test_multiple_pets_same_litter(async_session: AsyncSession, test_user: User):
    """
    Test that a breeding can have multiple pets.
    
    Verifies the one-to-many relationship between Breeding and Pet.
    Validates: Requirements 11.4
    """
    from datetime import date
    
    # Create a breeding
    breeding = Breeding(
        date_of_litter=date.today(),
        description="Test Breeding",
        is_active=True
    )
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    
    # Create multiple pets in the same breeding
    pet1 = Pet(name="Puppy 1", user_id=test_user.id, breeding_id=breeding.id, is_deleted=False)
    pet2 = Pet(name="Puppy 2", user_id=test_user.id, breeding_id=breeding.id, is_deleted=False)
    pet3 = Pet(name="Puppy 3", user_id=test_user.id, breeding_id=breeding.id, is_deleted=False)
    
    async_session.add_all([pet1, pet2, pet3])
    await async_session.commit()
    
    # Refresh breeding to load relationships
    await async_session.refresh(breeding)
    
    # Verify all pets are associated with the breeding
    assert len(breeding.pets) == 3
    pet_names = {pet.name for pet in breeding.pets}
    assert "Puppy 1" in pet_names
    assert "Puppy 2" in pet_names
    assert "Puppy 3" in pet_names


@pytest.mark.asyncio
async def test_pet_location_relationship(async_session: AsyncSession, test_user: User):
    """
    Test Pet → Location relationship.
    
    Verifies that a pet can be associated with a location.
    Validates: Requirements 11.4
    """
    # Create a location
    location = Location(
        name="Test Location",
        address1="123 Test St",
        city="Test City",
        state="TS",
        country="Test Country",
        zipcode="12345",
        location_type="pet",
        user_id=test_user.id
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Create a pet at the location
    pet = Pet(
        name="Test Pet",
        user_id=test_user.id,
        location_id=location.id,
        is_deleted=False
    )
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    
    # Verify the relationship
    assert pet.location_id == location.id
    assert pet.location is not None
    assert pet.location.id == location.id
    assert pet.location.name == "Test Location"
    
    # Verify reverse relationship
    await async_session.refresh(location)
    assert len(location.pets) > 0
    assert any(p.id == pet.id for p in location.pets)


@pytest.mark.asyncio
async def test_breed_colours_relationship(async_session: AsyncSession):
    """
    Test Breed → BreedColour relationship.
    
    Verifies that a breed can have multiple colors.
    Validates: Requirements 11.4
    """
    from app.models.breed import BreedColour
    
    # Create a breed
    breed = Breed(
        name="Test Breed",
        code="TB",
        group="Test Group"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Create multiple colors for the breed
    color1 = BreedColour(breed_id=breed.id, code="BLK", name="Black")
    color2 = BreedColour(breed_id=breed.id, code="WHT", name="White")
    color3 = BreedColour(breed_id=breed.id, code="BRN", name="Brown")
    
    async_session.add_all([color1, color2, color3])
    await async_session.commit()
    
    # Refresh breed to load relationships
    await async_session.refresh(breed)
    
    # Verify all colors are associated with the breed
    assert len(breed.colours) == 3
    color_names = {color.name for color in breed.colours}
    assert "Black" in color_names
    assert "White" in color_names
    assert "Brown" in color_names
