"""Property-based tests for litter operations."""

import pytest
from datetime import date, timedelta
from hypothesis import given, settings, strategies as st, HealthCheck
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.litter import Litter
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

# Date strategy for litter dates (reasonable range)
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
    Property 14: Litter Association
    
    For any Litter_Entity, multiple Pet_Entity records should be able to
    reference it via litter_id.
    
    Feature: laravel-to-fastapi-migration, Property 14: Litter Association
    Validates: Requirements 7.3
    """
    # Cache the user_id to avoid lazy loading issues in async context
    user_id = test_user.id
    
    # Create a litter
    litter = Litter(
        date_of_litter=litter_date,
        description=description,
        is_active=True,
    )
    
    async_session.add(litter)
    await async_session.commit()
    await async_session.refresh(litter)
    
    litter_id = litter.id
    
    # Create multiple pets associated with this litter
    created_pet_ids = []
    for name in pet_names:
        pet = Pet(
            user_id=user_id,
            name=name,
            litter_id=litter_id,
        )
        async_session.add(pet)
        created_pet_ids.append(pet)
    
    await async_session.commit()
    
    # Refresh all pets to get their IDs
    for pet in created_pet_ids:
        await async_session.refresh(pet)
    
    # Verify all pets reference the same litter
    for pet in created_pet_ids:
        assert pet.litter_id == litter_id, f"Pet {pet.id} should reference litter {litter_id}"
    
    # Query all pets for this litter
    query = select(Pet).where(Pet.litter_id == litter_id)
    result = await async_session.execute(query)
    litter_pets = result.scalars().all()
    
    # Verify the correct number of pets are associated
    assert len(litter_pets) == len(pet_names), \
        f"Expected {len(pet_names)} pets for litter, got {len(litter_pets)}"
    
    # Verify all created pets are in the results
    litter_pet_ids = {pet.id for pet in litter_pets}
    for pet in created_pet_ids:
        assert pet.id in litter_pet_ids, f"Pet {pet.id} should be in litter pets"
    
    # Verify the relationship works from litter to pets
    await async_session.refresh(litter)
    assert len(litter.pets) == len(pet_names), \
        f"Litter relationship should have {len(pet_names)} pets"
    
    for pet in litter.pets:
        assert pet.litter_id == litter_id, \
            f"Pet {pet.id} in relationship should reference litter {litter_id}"


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
    Property 15: Referential Integrity - Pet to Litter
    
    For any Pet_Entity creation or update with a litter_id, the litter_id should
    reference an existing Litter_Entity, or the operation should fail.
    
    Feature: laravel-to-fastapi-migration, Property 15: Referential Integrity - Pet to Litter
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
    
    # Test 1: Creating pet with valid litter_id should succeed
    # Create a litter first
    litter = Litter(
        date_of_litter=litter_date,
        description="Test litter",
        is_active=True,
    )
    
    async_session.add(litter)
    await async_session.commit()
    await async_session.refresh(litter)
    
    valid_litter_id = litter.id
    
    # Create pet with valid litter_id
    pet_with_litter = Pet(
        user_id=user_id,
        name=pet_name,
        litter_id=valid_litter_id,
    )
    
    async_session.add(pet_with_litter)
    await async_session.commit()
    await async_session.refresh(pet_with_litter)
    
    assert pet_with_litter.litter_id == valid_litter_id, \
        "Pet should have valid litter_id"
    
    # Verify the foreign key constraint is working
    query = select(Litter).where(Litter.id == pet_with_litter.litter_id)
    result = await async_session.execute(query)
    referenced_litter = result.scalar_one_or_none()
    
    assert referenced_litter is not None, \
        "Pet's litter_id should reference an existing litter"
    assert referenced_litter.id == valid_litter_id, \
        "Referenced litter should match the litter_id"
    
    # Test 2: Creating pet with non-existent litter_id should fail
    # Use a very large integer that doesn't exist
    non_existent_litter_id = 999999999
    
    pet_with_invalid_litter = Pet(
        user_id=user_id,
        name=f"{pet_name}_invalid",
        litter_id=non_existent_litter_id,
    )
    
    async_session.add(pet_with_invalid_litter)
    
    # This should raise an IntegrityError due to foreign key constraint
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await async_session.commit()
    
    # Rollback the failed transaction
    await async_session.rollback()
