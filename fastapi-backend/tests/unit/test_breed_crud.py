"""Unit tests for breed CRUD operations."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breed import Breed


@pytest.mark.asyncio
async def test_create_breed_with_valid_data(async_session: AsyncSession):
    """Test creating a breed with all valid fields."""
    breed = Breed(
        name="Golden Retriever",
        code="GR",
        group="Sporting"
    )
    
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    assert breed.id is not None
    assert isinstance(breed.id, int)
    assert breed.name == "Golden Retriever"
    assert breed.code == "GR"
    assert breed.group == "Sporting"
    assert breed.created_at is not None


@pytest.mark.asyncio
async def test_create_breed_minimal_data(async_session: AsyncSession):
    """Test creating a breed with only required fields (name)."""
    breed = Breed(name="Poodle")
    
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    assert breed.id is not None
    assert breed.name == "Poodle"
    assert breed.code is None
    assert breed.group is None


@pytest.mark.asyncio
async def test_list_breeds(async_session: AsyncSession):
    """Test listing all breeds."""
    # Create multiple breeds
    breed1 = Breed(name="Beagle", group="Hound")
    breed2 = Breed(name="Bulldog", group="Non-Sporting")
    breed3 = Breed(name="Chihuahua", group="Toy")
    
    async_session.add_all([breed1, breed2, breed3])
    await async_session.commit()
    
    # Query all breeds
    query = select(Breed).order_by(Breed.name)
    result = await async_session.execute(query)
    breeds = result.scalars().all()
    
    assert len(breeds) >= 3
    breed_names = [b.name for b in breeds]
    assert "Beagle" in breed_names
    assert "Bulldog" in breed_names
    assert "Chihuahua" in breed_names


@pytest.mark.asyncio
async def test_update_breed(async_session: AsyncSession):
    """Test updating a breed's information."""
    # Create breed
    breed = Breed(
        name="Original Name",
        code="ON",
        group="Original Group"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Update breed
    breed.name = "Updated Name"
    breed.code = "UN"
    breed.group = "Updated Group"
    
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Verify updates
    assert breed.name == "Updated Name"
    assert breed.code == "UN"
    assert breed.group == "Updated Group"
    assert breed.updated_at is not None


@pytest.mark.asyncio
async def test_update_breed_partial_fields(async_session: AsyncSession):
    """Test updating only specific fields of a breed."""
    # Create breed with multiple fields
    breed = Breed(
        name="Original",
        code="OR",
        group="Original Group"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Update only name
    breed.name = "Updated"
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Verify only name changed
    assert breed.name == "Updated"
    assert breed.code == "OR"
    assert breed.group == "Original Group"


@pytest.mark.asyncio
async def test_delete_breed(async_session: AsyncSession):
    """Test hard deletion of a breed."""
    # Create breed
    breed = Breed(name="To Be Deleted")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    breed_id = breed.id
    
    # Delete breed
    await async_session.delete(breed)
    await async_session.commit()
    
    # Verify breed no longer exists
    query = select(Breed).where(Breed.id == breed_id)
    result = await async_session.execute(query)
    deleted_breed = result.scalar_one_or_none()
    
    assert deleted_breed is None


@pytest.mark.asyncio
async def test_breed_name_uniqueness(async_session: AsyncSession):
    """Test that breed names should be unique."""
    # Create first breed
    breed1 = Breed(name="Unique Breed")
    async_session.add(breed1)
    await async_session.commit()
    
    # Attempt to create second breed with same name
    breed2 = Breed(name="Unique Breed")
    async_session.add(breed2)
    
    # This should raise an integrity error
    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
        await async_session.commit()


@pytest.mark.asyncio
async def test_get_breed_by_id(async_session: AsyncSession):
    """Test retrieving a breed by ID."""
    # Create breed
    breed = Breed(name="Test Breed", group="Test Group")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    breed_id = breed.id
    
    # Retrieve breed by ID
    query = select(Breed).where(Breed.id == breed_id)
    result = await async_session.execute(query)
    retrieved_breed = result.scalar_one_or_none()
    
    assert retrieved_breed is not None
    assert retrieved_breed.id == breed_id
    assert retrieved_breed.name == "Test Breed"
    assert retrieved_breed.group == "Test Group"


@pytest.mark.asyncio
async def test_breed_with_colours_relationship(async_session: AsyncSession):
    """Test breed with colours relationship."""
    from app.models.breed import BreedColour
    
    # Create breed
    breed = Breed(name="Labrador Retriever", group="Sporting")
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Add colours
    colour1 = BreedColour(breed_id=breed.id, code="BLK", name="Black")
    colour2 = BreedColour(breed_id=breed.id, code="YEL", name="Yellow")
    colour3 = BreedColour(breed_id=breed.id, code="CHO", name="Chocolate")
    
    async_session.add_all([colour1, colour2, colour3])
    await async_session.commit()
    await async_session.refresh(breed)
    
    # Access colours relationship
    assert len(breed.colours) == 3
    colour_names = {c.name for c in breed.colours}
    assert colour_names == {"Black", "Yellow", "Chocolate"}
