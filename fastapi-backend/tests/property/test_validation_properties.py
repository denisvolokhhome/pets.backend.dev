"""Property-based tests for schema validation."""
import uuid
from datetime import date, datetime

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from app.schemas.pet import PetCreate, PetUpdate
from app.schemas.breed import BreedCreate, BreedUpdate
from app.schemas.breeding import LitterCreate, LitterUpdate
from app.schemas.location import LocationCreate, LocationUpdate


# Custom strategies for generating test data
# Generate valid names that are not empty or whitespace-only
valid_names = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"),  # Exclude control characters
        blacklist_characters=("\r", "\n", "\t")
    )
).filter(lambda s: s.strip() != "")  # Ensure not whitespace-only
# Generate strings that are empty or only whitespace
empty_or_whitespace = st.sampled_from([
    "",  # empty string
    " ",  # single space
    "  ",  # multiple spaces
    "\t",  # tab
    "\n",  # newline
    "\r",  # carriage return
    " \t\n",  # mixed whitespace
    "   ",  # three spaces
])
negative_numbers = st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False)


class TestValidationErrorProperties:
    """Property-based tests for validation error responses."""
    
    @settings(max_examples=100)
    @given(name=empty_or_whitespace)
    def test_property_pet_empty_name_validation(self, name):
        """
        Property 23: Validation Error Response
        For any empty or whitespace-only name, pet creation should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            PetCreate(name=name)
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("name",) for error in errors)
    
    @settings(max_examples=100)
    @given(weight=negative_numbers)
    def test_property_pet_negative_weight_validation(self, weight):
        """
        Property 23: Validation Error Response
        For any negative weight value, pet creation should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            PetCreate(name="Test Pet", weight=weight)
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("weight",) for error in errors)
    
    @settings(max_examples=100)
    @given(name=empty_or_whitespace)
    def test_property_breed_empty_name_validation(self, name):
        """
        Property 23: Validation Error Response
        For any empty or whitespace-only name, breed creation should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            BreedCreate(name=name)
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("name",) for error in errors)
    
    @settings(max_examples=100)
    @given(name=empty_or_whitespace)
    def test_property_location_empty_name_validation(self, name):
        """
        Property 23: Validation Error Response
        For any empty or whitespace-only name, location creation should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            LocationCreate(
                name=name,
                address1="123 Main St",
                city="Springfield",
                state="IL",
                country="USA",
                zipcode="62701",
                location_type="user"
            )
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("name",) for error in errors)
    
    @settings(max_examples=100)
    @given(
        name=valid_names,
        address1=empty_or_whitespace
    )
    def test_property_location_empty_address_validation(self, name, address1):
        """
        Property 23: Validation Error Response
        For any empty or whitespace-only address, location creation should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            LocationCreate(
                name=name,
                address1=address1,
                city="Springfield",
                state="IL",
                country="USA",
                zipcode="62701",
                location_type="user"
            )
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("address1",) for error in errors)
    
    @settings(max_examples=100)
    @given(description=st.text())
    def test_property_litter_missing_date_validation(self, description):
        """
        Property 23: Validation Error Response
        For any breeding creation without required date, should raise ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        with pytest.raises(ValidationError) as exc_info:
            # Intentionally omit date_of_litter
            LitterCreate(description=description)
        
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any(error["loc"] == ("date_of_litter",) for error in errors)
    
    @settings(max_examples=100)
    @given(
        name=valid_names,
        breed_id=st.integers(),
        weight=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False)
    )
    def test_property_valid_pet_data_passes_validation(self, name, breed_id, weight):
        """
        Property 23: Validation Error Response
        For any valid pet data, creation should succeed without ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        # This should not raise ValidationError
        pet = PetCreate(name=name, breed_id=breed_id, weight=weight)
        assert pet.name == name
        assert pet.breed_id == breed_id
        assert pet.weight == weight
    
    @settings(max_examples=100)
    @given(
        name=valid_names,
        code=st.text(max_size=255) | st.none(),
        group=st.text() | st.none()
    )
    def test_property_valid_breed_data_passes_validation(self, name, code, group):
        """
        Property 23: Validation Error Response
        For any valid breed data, creation should succeed without ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        # This should not raise ValidationError
        breed = BreedCreate(name=name, code=code, group=group)
        assert breed.name == name
        assert breed.code == code
        assert breed.group == group
    
    @settings(max_examples=100)
    @given(
        date_of_litter=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)),
        description=st.text() | st.none(),
        is_active=st.booleans()
    )
    def test_property_valid_litter_data_passes_validation(self, date_of_litter, description, is_active):
        """
        Property 23: Validation Error Response
        For any valid breeding data, creation should succeed without ValidationError.
        
        Feature: laravel-to-fastapi-migration, Property 23: Validation Error Response
        Validates: Requirements 10.1
        """
        # This should not raise ValidationError
        breeding = LitterCreate(
            date_of_litter=date_of_litter,
            description=description,
            is_active=is_active
        )
        assert breeding.date_of_litter == date_of_litter
        assert breeding.description == description
        assert breeding.is_active == is_active
