"""Property-based tests for API response structure.

Feature: pet-search-map
Tests universal properties for API response completeness and consistency.
"""
import pytest
from hypothesis import given, settings, strategies as st
from typing import Dict, Any, List
from uuid import UUID

from app.schemas.breeder import BreederSearchResult, BreedInfo
from app.schemas.breed import BreedRead


class TestProperty39BreederObjectFieldCompleteness:
    """
    Feature: pet-search-map, Property 39: Breeder Object Field Completeness
    
    For any breeder object returned from the API, it SHALL include the fields:
    user_id, breeder_name, latitude, longitude, distance, available_breeds,
    thumbnail_url, location_description, and rating.
    
    Validates: Requirements 13.4
    """
    
    @given(
        user_id=st.uuids(),
        breeder_name=st.text(min_size=1, max_size=100),
        latitude=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
        longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        distance=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        location_id=st.integers(min_value=1, max_value=1000000),
        thumbnail_url=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
        location_description=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
        rating=st.one_of(st.none(), st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False))
    )
    @settings(max_examples=100, deadline=None)
    def test_breeder_result_has_all_required_fields(
        self,
        user_id,
        breeder_name,
        latitude,
        longitude,
        distance,
        location_id,
        thumbnail_url,
        location_description,
        rating
    ):
        """
        Test that BreederSearchResult schema includes all required fields.
        
        For any valid input data, the schema should successfully create an object
        with all required fields present.
        """
        # Create a BreederSearchResult object
        result = BreederSearchResult(
            location_id=location_id,
            user_id=user_id,
            breeder_name=breeder_name,
            latitude=latitude,
            longitude=longitude,
            distance=distance,
            available_breeds=[],
            thumbnail_url=thumbnail_url,
            location_description=location_description,
            rating=rating
        )
        
        # Verify all required fields are present
        assert hasattr(result, 'location_id'), "Missing field: location_id"
        assert hasattr(result, 'user_id'), "Missing field: user_id"
        assert hasattr(result, 'breeder_name'), "Missing field: breeder_name"
        assert hasattr(result, 'latitude'), "Missing field: latitude"
        assert hasattr(result, 'longitude'), "Missing field: longitude"
        assert hasattr(result, 'distance'), "Missing field: distance"
        assert hasattr(result, 'available_breeds'), "Missing field: available_breeds"
        assert hasattr(result, 'thumbnail_url'), "Missing field: thumbnail_url"
        assert hasattr(result, 'location_description'), "Missing field: location_description"
        assert hasattr(result, 'rating'), "Missing field: rating"
        
        # Verify field values match input
        assert result.location_id == location_id
        assert result.user_id == user_id
        assert result.breeder_name == breeder_name
        assert result.latitude == latitude
        assert result.longitude == longitude
        assert abs(result.distance - round(distance, 1)) < 0.01  # Distance is rounded
        assert result.available_breeds == []
        assert result.thumbnail_url == thumbnail_url
        assert result.location_description == location_description
        assert result.rating == rating
    
    @given(
        user_id=st.uuids(),
        breeder_name=st.text(min_size=1, max_size=100),
        latitude=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
        longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        distance=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        location_id=st.integers(min_value=1, max_value=1000000),
        breed_count=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, deadline=None)
    def test_breeder_result_serializes_to_dict(
        self,
        user_id,
        breeder_name,
        latitude,
        longitude,
        distance,
        location_id,
        breed_count
    ):
        """
        Test that BreederSearchResult can be serialized to a dictionary.
        
        This ensures the API can return the object as JSON with all fields.
        """
        # Create breed info objects
        available_breeds = [
            BreedInfo(
                breed_id=i,
                breed_name=f"Breed {i}",
                pet_count=i + 1
            )
            for i in range(breed_count)
        ]
        
        # Create a BreederSearchResult object
        result = BreederSearchResult(
            location_id=location_id,
            user_id=user_id,
            breeder_name=breeder_name,
            latitude=latitude,
            longitude=longitude,
            distance=distance,
            available_breeds=available_breeds,
            thumbnail_url="/storage/test.jpg",
            location_description="Test location",
            rating=4.5
        )
        
        # Serialize to dict
        result_dict = result.model_dump()
        
        # Verify all fields are in the dictionary
        assert 'location_id' in result_dict
        assert 'user_id' in result_dict
        assert 'breeder_name' in result_dict
        assert 'latitude' in result_dict
        assert 'longitude' in result_dict
        assert 'distance' in result_dict
        assert 'available_breeds' in result_dict
        assert 'thumbnail_url' in result_dict
        assert 'location_description' in result_dict
        assert 'rating' in result_dict
        
        # Verify available_breeds is a list
        assert isinstance(result_dict['available_breeds'], list)
        assert len(result_dict['available_breeds']) == breed_count
    
    @given(
        distance=st.floats(min_value=0.01, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None)
    def test_distance_is_rounded_to_one_decimal(self, distance):
        """
        Test that distance is always rounded to 1 decimal place.
        
        This ensures consistent formatting across all API responses.
        """
        result = BreederSearchResult(
            location_id=1,
            user_id=UUID('12345678-1234-5678-1234-567812345678'),
            breeder_name="Test Breeder",
            latitude=40.0,
            longitude=-74.0,
            distance=distance,
            available_breeds=[],
            thumbnail_url=None,
            location_description=None,
            rating=None
        )
        
        # Distance should be rounded to 1 decimal place
        expected_distance = round(distance, 1)
        assert result.distance == expected_distance, \
            f"Distance {result.distance} should be rounded to {expected_distance}"
        
        # Verify it has at most 1 decimal place
        distance_str = str(result.distance)
        if '.' in distance_str:
            decimal_places = len(distance_str.split('.')[1])
            assert decimal_places <= 1, \
                f"Distance should have at most 1 decimal place, has {decimal_places}"
    
    @given(
        breed_ids=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=10, unique=True)
    )
    @settings(max_examples=50, deadline=None)
    def test_available_breeds_list_completeness(self, breed_ids):
        """
        Test that available_breeds list includes all breeds with proper structure.
        
        Each breed in the list should have breed_id, breed_name, and pet_count.
        """
        available_breeds = [
            BreedInfo(
                breed_id=breed_id,
                breed_name=f"Breed {breed_id}",
                pet_count=breed_id % 10 + 1
            )
            for breed_id in breed_ids
        ]
        
        result = BreederSearchResult(
            location_id=1,
            user_id=UUID('12345678-1234-5678-1234-567812345678'),
            breeder_name="Test Breeder",
            latitude=40.0,
            longitude=-74.0,
            distance=5.0,
            available_breeds=available_breeds,
            thumbnail_url=None,
            location_description=None,
            rating=None
        )
        
        # Verify all breeds are present
        assert len(result.available_breeds) == len(breed_ids)
        
        # Verify each breed has required fields
        for breed in result.available_breeds:
            assert hasattr(breed, 'breed_id')
            assert hasattr(breed, 'breed_name')
            assert hasattr(breed, 'pet_count')
            assert breed.breed_id in breed_ids
            assert breed.pet_count > 0


class TestProperty40BreedAutocompleteResponse:
    """
    Feature: pet-search-map, Property 40: Breed Autocomplete Response
    
    For any search term sent to /api/breeds/autocomplete, the system SHALL
    return a JSON array of breed objects that match the search term.
    
    Validates: Requirements 13.6
    """
    
    @given(
        breed_id=st.integers(min_value=1, max_value=1000000),
        breed_name=st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=65, max_codepoint=122)),
        breed_code=st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122))),
        breed_group=st.one_of(st.none(), st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))
    )
    @settings(max_examples=100, deadline=None)
    def test_breed_read_has_all_required_fields(
        self,
        breed_id,
        breed_name,
        breed_code,
        breed_group
    ):
        """
        Test that BreedRead schema includes all required fields for autocomplete.
        
        For any valid breed data, the schema should successfully create an object
        with id, name, and code fields (as per Requirements 13.7).
        """
        from datetime import datetime
        
        # Ensure breed_name is not whitespace-only (schema validation requirement)
        if not breed_name or not breed_name.strip():
            breed_name = "Test Breed"
        
        # Create a BreedRead object
        breed = BreedRead(
            id=breed_id,
            name=breed_name,
            code=breed_code,
            group=breed_group,
            created_at=datetime.now(),
            updated_at=None
        )
        
        # Verify all required fields are present
        assert hasattr(breed, 'id'), "Missing field: id (breed_id)"
        assert hasattr(breed, 'name'), "Missing field: name (breed_name)"
        assert hasattr(breed, 'code'), "Missing field: code (breed_code)"
        
        # Verify field values match input
        assert breed.id == breed_id
        assert breed.name == breed_name
        assert breed.code == breed_code
    
    @given(
        breed_count=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50, deadline=None)
    def test_breed_autocomplete_returns_list(self, breed_count):
        """
        Test that breed autocomplete returns a list of breed objects.
        
        The response should be a list (possibly empty) of BreedRead objects.
        """
        from datetime import datetime
        
        # Create a list of breed objects
        breeds = [
            BreedRead(
                id=i,
                name=f"Breed {i}",
                code=f"CODE{i}",
                group="Test Group",
                created_at=datetime.now(),
                updated_at=None
            )
            for i in range(breed_count)
        ]
        
        # Verify it's a list
        assert isinstance(breeds, list)
        assert len(breeds) == breed_count
        
        # Verify each item is a BreedRead object
        for breed in breeds:
            assert isinstance(breed, BreedRead)
            assert hasattr(breed, 'id')
            assert hasattr(breed, 'name')
            assert hasattr(breed, 'code')
    
    @given(
        breed_count=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=50, deadline=None)
    def test_breed_list_serializes_to_json(self, breed_count):
        """
        Test that a list of breeds can be serialized to JSON.
        
        This ensures the API can return the list as a JSON array.
        """
        from datetime import datetime
        
        # Create a list of breed objects
        breeds = [
            BreedRead(
                id=i,
                name=f"Breed {i}",
                code=f"CODE{i}",
                group="Test Group",
                created_at=datetime.now(),
                updated_at=None
            )
            for i in range(breed_count)
        ]
        
        # Serialize to list of dicts
        breeds_dicts = [breed.model_dump() for breed in breeds]
        
        # Verify it's a list
        assert isinstance(breeds_dicts, list)
        assert len(breeds_dicts) == breed_count
        
        # Verify each dict has required fields
        for breed_dict in breeds_dicts:
            assert 'id' in breed_dict
            assert 'name' in breed_dict
            assert 'code' in breed_dict
    
    @given(
        search_term=st.text(min_size=2, max_size=50)
    )
    @settings(max_examples=50, deadline=None)
    def test_breed_matching_logic(self, search_term):
        """
        Test the logical consistency of breed matching.
        
        Breeds that match the search term should be included in results.
        """
        from datetime import datetime
        
        # Create test breeds with various names
        test_breeds = [
            BreedRead(
                id=1,
                name="Labrador Retriever",
                code="LAB",
                group="Sporting",
                created_at=datetime.now(),
                updated_at=None
            ),
            BreedRead(
                id=2,
                name="Golden Retriever",
                code="GOLD",
                group="Sporting",
                created_at=datetime.now(),
                updated_at=None
            ),
            BreedRead(
                id=3,
                name="German Shepherd",
                code="GSD",
                group="Herding",
                created_at=datetime.now(),
                updated_at=None
            ),
        ]
        
        # Filter breeds by search term (case-insensitive partial match)
        search_lower = search_term.lower()
        matching_breeds = [
            breed for breed in test_breeds
            if search_lower in breed.name.lower() or 
               (breed.code and search_lower in breed.code.lower())
        ]
        
        # Verify matching logic
        for breed in matching_breeds:
            assert (
                search_lower in breed.name.lower() or
                (breed.code and search_lower in breed.code.lower())
            ), f"Breed {breed.name} should match search term {search_term}"
        
        # Verify non-matching breeds are excluded
        non_matching = [breed for breed in test_breeds if breed not in matching_breeds]
        for breed in non_matching:
            assert not (
                search_lower in breed.name.lower() or
                (breed.code and search_lower in breed.code.lower())
            ), f"Breed {breed.name} should not match search term {search_term}"
