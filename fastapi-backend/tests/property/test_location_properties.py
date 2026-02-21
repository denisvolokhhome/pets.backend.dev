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


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    num_users=st.integers(min_value=2, max_value=5),
    locations_per_user=st.integers(min_value=1, max_value=3),
)
async def test_property_location_user_isolation(
    num_users: int,
    locations_per_user: int,
    async_session: AsyncSession,
):
    """
    Property 2: Location User Isolation
    
    For any authenticated user, all location retrieval operations should return
    only locations where location.user_id equals the authenticated user's ID.
    
    Feature: user-profile-settings, Property 2: Location User Isolation
    Validates: Requirements 7.3, 7.5
    """
    # Clean up any existing data
    from sqlalchemy import delete
    await async_session.execute(delete(Location))
    await async_session.execute(delete(User))
    await async_session.commit()
    
    # Create multiple users
    users = []
    for i in range(num_users):
        import uuid as uuid_module
        user = User(
            email=f"user-{uuid_module.uuid4()}@example.com",
            hashed_password="hashed_password",
            name=f"User {i}",
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        async_session.add(user)
        users.append(user)
    
    await async_session.commit()
    
    # Refresh all users to get their IDs
    for user in users:
        await async_session.refresh(user)
    
    # Create locations for each user
    user_location_map = {}
    for user in users:
        user_locations = []
        for j in range(locations_per_user):
            location = Location(
                user_id=user.id,
                name=f"Location {j} for {user.name}",
                address1=f"{j} Test Street",
                city="Test City",
                state="Test State",
                country="Test Country",
                zipcode="12345",
                location_type="user",
            )
            async_session.add(location)
            user_locations.append(location)
        user_location_map[user.id] = user_locations
    
    await async_session.commit()
    
    # Refresh all locations
    for locations in user_location_map.values():
        for location in locations:
            await async_session.refresh(location)
    
    # For each user, verify they can only see their own locations
    for user in users:
        # Query locations for this user (simulating API endpoint behavior)
        query = select(Location).where(Location.user_id == user.id)
        result = await async_session.execute(query)
        retrieved_locations = result.scalars().all()
        
        # Verify correct number of locations returned
        assert len(retrieved_locations) == locations_per_user, \
            f"User {user.id} should have {locations_per_user} locations, got {len(retrieved_locations)}"
        
        # Verify all returned locations belong to this user
        for location in retrieved_locations:
            assert location.user_id == user.id, \
                f"Location {location.id} has wrong user_id: {location.user_id} != {user.id}"
        
        # Verify no locations from other users are returned
        retrieved_location_ids = {loc.id for loc in retrieved_locations}
        for other_user_id, other_locations in user_location_map.items():
            if other_user_id != user.id:
                for other_location in other_locations:
                    assert other_location.id not in retrieved_location_ids, \
                        f"User {user.id} should not see location {other_location.id} from user {other_user_id}"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,  # Disable deadline for API tests which can be slower
)
@given(
    num_pets=st.integers(min_value=1, max_value=3),
)
async def test_property_location_deletion_constraint(
    num_pets: int,
    async_session: AsyncSession,
    test_user: User,
    test_breed,
):
    """
    Property 4: Location Deletion Constraint
    
    For any location that has associated pets (foreign key references),
    attempting to delete the location via the API should fail with a 409 Conflict error.
    
    Feature: user-profile-settings, Property 4: Location Deletion Constraint
    Validates: Requirements 4.10
    """
    from app.models.pet import Pet
    from sqlalchemy import delete
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.database import get_async_session
    from app.dependencies import current_active_user
    
    # Clean up any existing data
    await async_session.execute(delete(Pet))
    await async_session.execute(delete(Location))
    await async_session.commit()
    
    # Create a location
    location = Location(
        user_id=test_user.id,
        name="Test Location",
        address1="123 Test St",
        city="Test City",
        state="Test State",
        country="Test Country",
        zipcode="12345",
        location_type="user",
    )
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Create pets associated with this location
    pets = []
    for i in range(num_pets):
        pet = Pet(
            user_id=test_user.id,
            breed_id=test_breed.id,
            location_id=location.id,
            name=f"Pet {i}",
            gender="Male",
            is_puppy=True,
        )
        async_session.add(pet)
        pets.append(pet)
    
    await async_session.commit()
    
    # Refresh all pets
    for pet in pets:
        await async_session.refresh(pet)
    
    # Verify pets are associated with the location
    for pet in pets:
        assert pet.location_id == location.id, \
            f"Pet {pet.id} should be associated with location {location.id}"
    
    # Set up test client with authentication
    async def override_get_async_session():
        yield async_session
    
    async def override_current_active_user():
        return test_user
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[current_active_user] = override_current_active_user
    
    transport = ASGITransport(app=app)
    
    # Attempt to delete the location via API - should fail with 409 Conflict
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(f"/api/locations/{location.id}")
        
        # Verify deletion was prevented with 409 Conflict
        assert response.status_code == 409, \
            f"Expected 409 Conflict when deleting location with {num_pets} associated pets, got {response.status_code}"
        
        # Verify error message mentions associated pets
        data = response.json()
        assert "detail" in data, "Response should contain error detail"
        error_message = data["detail"].lower()
        assert "associated pet" in error_message or "pet" in error_message, \
            f"Error message should mention associated pets: {data['detail']}"
    
    # Clean up overrides
    app.dependency_overrides.clear()
    
    # Verify location still exists in database
    query = select(Location).where(Location.id == location.id)
    result = await async_session.execute(query)
    existing_location = result.scalar_one_or_none()
    
    assert existing_location is not None, \
        "Location should still exist after failed deletion attempt"
    assert existing_location.id == location.id, \
        "Location ID should match original location"


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    # Generate field values that might be missing or whitespace
    name=st.one_of(st.none(), st.just(""), st.just("   "), location_name_strategy),
    address1=st.one_of(st.none(), st.just(""), st.just("   "), address_strategy),
    city=st.one_of(st.none(), st.just(""), st.just("   "), city_strategy),
    state=st.one_of(st.none(), st.just(""), st.just("   "), state_strategy),
    country=st.one_of(st.none(), st.just(""), st.just("   "), country_strategy),
    zipcode=st.one_of(st.none(), st.just(""), st.just("   "), zipcode_strategy),
)
async def test_property_required_location_fields(
    name,
    address1,
    city,
    state,
    country,
    zipcode,
    async_session: AsyncSession,
    test_user: User,
):
    """
    Property 6: Required Location Fields
    
    For any location creation or update request, if any required field
    (name, address1, city, state, country, zipcode) is missing or contains
    only whitespace, the request should be rejected with a validation error.
    
    Feature: user-profile-settings, Property 6: Required Location Fields
    Validates: Requirements 4.6
    """
    from pydantic import ValidationError
    from app.schemas.location import LocationCreate
    
    # Check if any required field is missing or whitespace
    def is_invalid(value):
        return value is None or (isinstance(value, str) and not value.strip())
    
    has_invalid_field = (
        is_invalid(name) or
        is_invalid(address1) or
        is_invalid(city) or
        is_invalid(state) or
        is_invalid(country) or
        is_invalid(zipcode)
    )
    
    # Attempt to create location with Pydantic schema validation
    validation_failed = False
    try:
        location_data = LocationCreate(
            name=name,
            address1=address1,
            address2=None,
            city=city,
            state=state,
            country=country,
            zipcode=zipcode,
            location_type="user",
        )
    except (ValidationError, ValueError, TypeError) as e:
        validation_failed = True
        error_message = str(e)
        
        # Verify the error mentions the missing/invalid field
        assert any(field in error_message.lower() for field in 
                  ["name", "address1", "city", "state", "country", "zipcode"]), \
            f"Validation error should mention the invalid field: {error_message}"
    
    # If any required field is invalid, validation should have failed
    if has_invalid_field:
        assert validation_failed, \
            f"Validation should have failed for invalid fields: " \
            f"name={name!r}, address1={address1!r}, city={city!r}, " \
            f"state={state!r}, country={country!r}, zipcode={zipcode!r}"
    else:
        # If all fields are valid, validation should have succeeded
        assert not validation_failed, \
            f"Validation should have succeeded for valid fields"
        
        # Verify the location can be created in the database
        location = Location(
            user_id=test_user.id,
            name=location_data.name,
            address1=location_data.address1,
            address2=location_data.address2,
            city=location_data.city,
            state=location_data.state,
            country=location_data.country,
            zipcode=location_data.zipcode,
            location_type=location_data.location_type,
        )
        async_session.add(location)
        await async_session.commit()
        await async_session.refresh(location)
        
        # Verify all required fields are set
        assert location.name == name
        assert location.address1 == address1
        assert location.city == city
        assert location.state == state
        assert location.country == country
        assert location.zipcode == zipcode
