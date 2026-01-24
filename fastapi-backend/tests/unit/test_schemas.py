"""Unit tests for Pydantic schema validation."""
import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserUpdate, UserRead
from app.schemas.pet import PetCreate, PetUpdate, PetRead
from app.schemas.breed import BreedCreate, BreedUpdate, BreedRead, BreedColourCreate
from app.schemas.litter import LitterCreate, LitterUpdate, LitterRead
from app.schemas.location import LocationCreate, LocationUpdate, LocationRead


class TestUserSchemas:
    """Test user schema validation."""
    
    def test_user_create_with_valid_data(self):
        """Test creating user schema with valid data."""
        user_data = {
            "email": "test@example.com",
            "password": "securepassword123"
        }
        user = UserCreate(**user_data)
        assert user.email == "test@example.com"
        assert user.password == "securepassword123"
    
    def test_user_create_with_invalid_email(self):
        """Test that invalid email is accepted (fastapi-users doesn't validate email format by default)."""
        # Note: fastapi-users BaseUserCreate doesn't enforce email format validation
        # This is intentional to allow flexibility in email formats
        user = UserCreate(email="not-an-email", password="password123")
        assert user.email == "not-an-email"
    
    def test_user_create_missing_required_fields(self):
        """Test that missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(email="test@example.com")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("password",) for error in errors)
    
    def test_user_update_with_partial_data(self):
        """Test updating user with partial data."""
        user_update = UserUpdate(email="newemail@example.com")
        assert user_update.email == "newemail@example.com"
        assert user_update.password is None


class TestPetSchemas:
    """Test pet schema validation."""
    
    def test_pet_create_with_valid_data(self):
        """Test creating pet schema with valid data."""
        pet_data = {
            "name": "Buddy",
            "breed_id": 1,
            "microchip": "123456789",
            "date_of_birth": date(2023, 1, 15)
        }
        pet = PetCreate(**pet_data)
        assert pet.name == "Buddy"
        assert pet.breed_id == 1
        assert pet.microchip == "123456789"
    
    def test_pet_create_with_empty_name(self):
        """Test that empty name raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PetCreate(name="")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("name",) for error in errors)
    
    def test_pet_create_with_negative_weight(self):
        """Test that negative weight raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PetCreate(name="Buddy", weight=-5.0)
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("weight",) for error in errors)
    
    def test_pet_create_with_null_optional_fields(self):
        """Test creating pet with null optional fields."""
        pet = PetCreate(name="Buddy")
        assert pet.name == "Buddy"
        assert pet.breed_id is None
        assert pet.microchip is None
        assert pet.vaccination is None
    
    def test_pet_update_with_partial_data(self):
        """Test updating pet with partial data."""
        pet_update = PetUpdate(name="New Name", weight=25.5)
        assert pet_update.name == "New Name"
        assert pet_update.weight == 25.5
        assert pet_update.breed_id is None
    
    def test_pet_read_from_orm(self):
        """Test pet read schema can be created from ORM attributes."""
        # Simulate ORM object attributes
        pet_data = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "name": "Buddy",
            "breed_id": 1,
            "litter_id": None,
            "location_id": None,
            "date_of_birth": None,
            "gender": None,
            "weight": None,
            "description": None,
            "is_puppy": None,
            "microchip": "123456789",
            "vaccination": None,
            "health_certificate": None,
            "deworming": None,
            "birth_certificate": None,
            "has_microchip": None,
            "has_vaccination": None,
            "has_healthcertificate": None,
            "has_dewormed": None,
            "has_birthcertificate": None,
            "image_path": None,
            "image_file_name": None,
            "is_deleted": False,
            "error": None,
            "created_at": datetime.now(),
            "updated_at": None
        }
        pet = PetRead(**pet_data)
        assert pet.name == "Buddy"
        assert pet.is_deleted is False


class TestBreedSchemas:
    """Test breed schema validation."""
    
    def test_breed_create_with_valid_data(self):
        """Test creating breed schema with valid data."""
        breed_data = {
            "name": "Labrador Retriever",
            "code": "LAB",
            "group": "Sporting"
        }
        breed = BreedCreate(**breed_data)
        assert breed.name == "Labrador Retriever"
        assert breed.code == "LAB"
        assert breed.group == "Sporting"
    
    def test_breed_create_with_empty_name(self):
        """Test that empty name raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            BreedCreate(name="")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("name",) for error in errors)
    
    def test_breed_create_with_null_optional_fields(self):
        """Test creating breed with null optional fields."""
        breed = BreedCreate(name="Golden Retriever")
        assert breed.name == "Golden Retriever"
        assert breed.code is None
        assert breed.group is None
    
    def test_breed_colour_create_with_valid_data(self):
        """Test creating breed colour schema with valid data."""
        colour_data = {
            "breed_id": 1,
            "code": "BLK",
            "name": "Black"
        }
        colour = BreedColourCreate(**colour_data)
        assert colour.breed_id == 1
        assert colour.code == "BLK"
        assert colour.name == "Black"


class TestLitterSchemas:
    """Test litter schema validation."""
    
    def test_litter_create_with_valid_data(self):
        """Test creating litter schema with valid data."""
        litter_data = {
            "date_of_litter": date(2023, 6, 15),
            "description": "First litter of the year",
            "is_active": True
        }
        litter = LitterCreate(**litter_data)
        assert litter.date_of_litter == date(2023, 6, 15)
        assert litter.description == "First litter of the year"
        assert litter.is_active is True
    
    def test_litter_create_missing_required_date(self):
        """Test that missing date raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            LitterCreate(description="Test litter")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("date_of_litter",) for error in errors)
    
    def test_litter_create_with_default_is_active(self):
        """Test that is_active defaults to True."""
        litter = LitterCreate(date_of_litter=date(2023, 6, 15))
        assert litter.is_active is True
    
    def test_litter_update_with_partial_data(self):
        """Test updating litter with partial data."""
        litter_update = LitterUpdate(is_active=False)
        assert litter_update.is_active is False
        assert litter_update.date_of_litter is None


class TestLocationSchemas:
    """Test location schema validation."""
    
    def test_location_create_with_valid_data(self):
        """Test creating location schema with valid data."""
        location_data = {
            "name": "Main Kennel",
            "address1": "123 Main St",
            "address2": "Suite 100",
            "city": "Springfield",
            "state": "IL",
            "country": "USA",
            "zipcode": "62701",
            "location_type": "user"
        }
        location = LocationCreate(**location_data)
        assert location.name == "Main Kennel"
        assert location.address1 == "123 Main St"
        assert location.city == "Springfield"
    
    def test_location_create_missing_required_fields(self):
        """Test that missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            LocationCreate(
                name="Main Kennel",
                address1="123 Main St"
                # Missing city, state, country, zipcode, location_type
            )
        
        errors = exc_info.value.errors()
        error_fields = [error["loc"][0] for error in errors]
        assert "city" in error_fields
        assert "state" in error_fields
        assert "country" in error_fields
        assert "zipcode" in error_fields
        assert "location_type" in error_fields
    
    def test_location_create_with_empty_strings(self):
        """Test that empty strings raise validation errors."""
        with pytest.raises(ValidationError) as exc_info:
            LocationCreate(
                name="",
                address1="123 Main St",
                city="Springfield",
                state="IL",
                country="USA",
                zipcode="62701",
                location_type="user"
            )
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("name",) for error in errors)
    
    def test_location_update_with_partial_data(self):
        """Test updating location with partial data."""
        location_update = LocationUpdate(city="New City", state="CA")
        assert location_update.city == "New City"
        assert location_update.state == "CA"
        assert location_update.name is None
