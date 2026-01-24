"""Property-based tests for location operations."""

import uuid
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import Location
from app.models.user import User


# Hypothesis strategies
# Filter out null bytes, surrogates, and other problematic characters for PostgreSQL
location_name_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

address_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

city_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

state_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

country_strategy = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

zipcode_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f'
    )
).filter(lambda x: x.strip())

location_type_strategy = st.sampled_from(["user", "pet"])


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    name=location_name_strategy,
    address1=address_strategy,
    city=city_strategy,
    state=state_strategy,
    country=country_strategy,
    zipcode=zipcode_strategy,
    location_type=location_type_strategy,
)
async def test_property_location_ownership_association(
    name: str,
    address1: str,
    city: str,
    state: str,
    country: str,
    zipcode: str,
    location_type: str,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 16: Location Ownership Association
    
    For any created Location_Entity, it should have a valid user_id that references
    an existing User_Entity.
    
    Feature: laravel-to-fastapi-migration, Property 16: Location Ownership Association
    Validates: Requirements 8.3
    """
    # Create location with test user
    location = Location(
        user_id=test_user.id,
        name=name,
        address1=address1,
        address2=None,
        city=city,
        state=state,
        country=country,
        zipcode=zipcode,
        location_type=location_type,
    )
    
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Verify location has valid user_id
    assert location.user_id is not None
    assert isinstance(location.user_id, uuid.UUID)
    assert location.user_id == test_user.id
    
    # Verify user_id references an existing user
    query = select(User).where(User.id == location.user_id)
    result = await async_session.execute(query)
    user = result.scalar_one_or_none()
    
    assert user is not None
    assert user.id == test_user.id
    
    # Verify relationship works
    assert location.user is not None
    assert location.user.id == test_user.id


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    location_names=st.lists(location_name_strategy, min_size=1, max_size=5),
)
async def test_property_user_location_filtering(
    location_names: list[str],
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 17: User Location Filtering
    
    For any user querying their locations, all returned locations should have
    user_id matching the authenticated user's ID.
    
    Feature: laravel-to-fastapi-migration, Property 17: User Location Filtering
    Validates: Requirements 8.4
    """
    # Clean up any existing locations from previous Hypothesis examples
    # This ensures each example starts with a clean state
    from sqlalchemy import delete
    await async_session.execute(delete(Location))
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
    
    # Create locations for test_user
    for name in location_names:
        location = Location(
            user_id=test_user.id,
            name=name,
            address1="123 Test St",
            city="Test City",
            state="Test State",
            country="Test Country",
            zipcode="12345",
            location_type="user",
        )
        async_session.add(location)
    
    # Create one location for other_user
    other_location = Location(
        user_id=other_user.id,
        name="Other Location",
        address1="456 Other St",
        city="Other City",
        state="Other State",
        country="Other Country",
        zipcode="67890",
        location_type="user",
    )
    async_session.add(other_location)
    
    await async_session.commit()
    
    # Query locations for test_user (user location filtering)
    query = select(Location).where(Location.user_id == test_user.id)
    result = await async_session.execute(query)
    user_locations = result.scalars().all()
    
    # Verify all returned locations belong to test_user
    assert len(user_locations) == len(location_names), f"Expected {len(location_names)} locations, got {len(user_locations)}"
    
    for location in user_locations:
        assert location.user_id == test_user.id, f"Location {location.id} has wrong user_id: {location.user_id} != {test_user.id}"
    
    # Verify no locations from other_user are returned
    location_ids = {location.id for location in user_locations}
    assert other_location.id not in location_ids, "Other user's location should not be in results"
