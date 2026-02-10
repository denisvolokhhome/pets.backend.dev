"""Unit tests for Pydantic schema validation."""
import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserUpdate, UserRead
from app.schemas.pet import PetCreate, PetUpdate, PetRead
from app.schemas.breed import BreedCreate, BreedUpdate, BreedRead, BreedColourCreate
from app.schemas.breeding import LitterCreate, LitterUpdate, LitterRead
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
    
    def test_user_read_with_profile_fields(self):
        """Test reading user schema with new profile fields."""
        user_data = {
            "id": uuid.uuid4(),
            "email": "breeder@example.com",
            "is_active": True,
            "is_superuser": False,
            "is_verified": True,
            "created_at": datetime.now(),
            "updated_at": None,
            "breedery_name": "Golden Paws Kennel",
            "profile_image_path": "/storage/app/profile_123.jpg",
            "breedery_description": "Premium golden retriever breeder",
            "search_tags": ["golden retriever", "family dogs", "AKC certified"]
        }
        user = UserRead(**user_data)
        assert user.breedery_name == "Golden Paws Kennel"
        assert user.profile_image_path == "/storage/app/profile_123.jpg"
        assert user.breedery_description == "Premium golden retriever breeder"
        assert user.search_tags == ["golden retriever", "family dogs", "AKC certified"]
    
    def test_user_read_with_null_profile_fields(self):
        """Test reading user schema with null profile fields."""
        user_data = {
            "id": uuid.uuid4(),
            "email": "newuser@example.com",
            "is_active": True,
            "is_superuser": False,
            "is_verified": False,
            "created_at": datetime.now(),
            "updated_at": None,
            "breedery_name": None,
            "profile_image_path": None,
            "breedery_description": None,
            "search_tags": None
        }
        user = UserRead(**user_data)
        assert user.breedery_name is None
        assert user.profile_image_path is None
        assert user.breedery_description is None
        assert user.search_tags is None
    
    def test_user_read_without_profile_fields(self):
        """Test reading user schema without providing profile fields (should default to None)."""
        user_data = {
            "id": uuid.uuid4(),
            "email": "minimal@example.com",
            "is_active": True,
            "is_superuser": False,
            "is_verified": False,
            "created_at": datetime.now()
        }
        user = UserRead(**user_data)
        assert user.breedery_name is None
        assert user.profile_image_path is None
        assert user.breedery_description is None
        assert user.search_tags is None
    
    def test_user_update_with_profile_fields(self):
        """Test updating user with profile fields."""
        user_update = UserUpdate(
            breedery_name="Updated Kennel Name",
            breedery_description="Updated description",
            search_tags=["labrador", "puppies"]
        )
        assert user_update.breedery_name == "Updated Kennel Name"
        assert user_update.breedery_description == "Updated description"
        assert user_update.search_tags == ["labrador", "puppies"]
        assert user_update.email is None
        assert user_update.password is None
    
    def test_user_update_with_empty_search_tags(self):
        """Test updating user with empty search tags list."""
        user_update = UserUpdate(search_tags=[])
        assert user_update.search_tags == []
    
    def test_user_update_profile_fields_optional(self):
        """Test that profile fields are optional in update."""
        user_update = UserUpdate(email="updated@example.com")
        assert user_update.email == "updated@example.com"
        assert user_update.breedery_name is None
        assert user_update.breedery_description is None
        assert user_update.search_tags is None
    
    def test_profile_image_response_schema(self):
        """Test ProfileImageResponse schema."""
        from app.schemas.user import ProfileImageResponse
        
        response_data = {
            "profile_image_path": "/storage/app/profile_abc123.jpg",
            "message": "Profile image uploaded successfully"
        }
        response = ProfileImageResponse(**response_data)
        assert response.profile_image_path == "/storage/app/profile_abc123.jpg"
        assert response.message == "Profile image uploaded successfully"
    
    def test_profile_image_response_missing_fields(self):
        """Test that ProfileImageResponse requires all fields."""
        from app.schemas.user import ProfileImageResponse
        
        with pytest.raises(ValidationError) as exc_info:
            ProfileImageResponse(profile_image_path="/storage/app/image.jpg")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("message",) for error in errors)


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
            "breeding_id": None,
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
    """Test breeding schema validation."""
    
    def test_litter_create_with_valid_data(self):
        """Test creating breeding schema with valid data."""
        breeding_data = {
            "description": "First breeding of the year"
        }
        breeding = LitterCreate(**breeding_data)
        assert breeding.description == "First breeding of the year"
    
    def test_litter_create_with_no_description(self):
        """Test creating breeding with no description."""
        breeding = LitterCreate()
        assert breeding.description is None
    
    def test_litter_update_with_partial_data(self):
        """Test updating breeding with partial data."""
        litter_update = LitterUpdate(description="Updated description")
        assert litter_update.description == "Updated description"
    
    def test_pet_assignment_with_valid_data(self):
        """Test PetAssignment validates exactly 2 pets."""
        from app.schemas.breeding import PetAssignment
        
        pet_ids = [uuid.uuid4(), uuid.uuid4()]
        assignment = PetAssignment(pet_ids=pet_ids)
        assert len(assignment.pet_ids) == 2
        assert assignment.pet_ids[0] != assignment.pet_ids[1]
    
    def test_pet_assignment_with_one_pet(self):
        """Test PetAssignment rejects single pet."""
        from app.schemas.breeding import PetAssignment
        
        with pytest.raises(ValidationError) as exc_info:
            PetAssignment(pet_ids=[uuid.uuid4()])
        
        errors = exc_info.value.errors()
        assert any("at least 2 items" in str(error["msg"]).lower() for error in errors)
    
    def test_pet_assignment_with_three_pets(self):
        """Test PetAssignment rejects more than 2 pets."""
        from app.schemas.breeding import PetAssignment
        
        with pytest.raises(ValidationError) as exc_info:
            PetAssignment(pet_ids=[uuid.uuid4(), uuid.uuid4(), uuid.uuid4()])
        
        errors = exc_info.value.errors()
        assert any("at most 2 items" in str(error["msg"]).lower() for error in errors)
    
    def test_pet_assignment_with_duplicate_pets(self):
        """Test PetAssignment rejects same pet twice."""
        from app.schemas.breeding import PetAssignment
        
        pet_id = uuid.uuid4()
        with pytest.raises(ValidationError) as exc_info:
            PetAssignment(pet_ids=[pet_id, pet_id])
        
        errors = exc_info.value.errors()
        assert any("cannot assign same pet twice" in str(error["msg"]).lower() for error in errors)
    
    def test_puppy_input_with_valid_data(self):
        """Test PuppyInput with valid data."""
        from app.schemas.breeding import PuppyInput
        
        puppy_data = {
            "name": "Max",
            "gender": "Male",
            "birth_date": date(2024, 1, 15),
            "microchip": "123456789"
        }
        puppy = PuppyInput(**puppy_data)
        assert puppy.name == "Max"
        assert puppy.gender == "Male"
        assert puppy.birth_date == date(2024, 1, 15)
        assert puppy.microchip == "123456789"
    
    def test_puppy_input_with_female_gender(self):
        """Test PuppyInput validates Female gender."""
        from app.schemas.breeding import PuppyInput
        
        puppy_data = {
            "name": "Bella",
            "gender": "Female",
            "birth_date": date(2024, 1, 15)
        }
        puppy = PuppyInput(**puppy_data)
        assert puppy.gender == "Female"
    
    def test_puppy_input_with_invalid_gender(self):
        """Test PuppyInput rejects invalid gender values."""
        from app.schemas.breeding import PuppyInput
        
        with pytest.raises(ValidationError) as exc_info:
            PuppyInput(
                name="Max",
                gender="Unknown",
                birth_date=date(2024, 1, 15)
            )
        
        errors = exc_info.value.errors()
        assert any("gender must be male or female" in str(error["msg"]).lower() for error in errors)
    
    def test_puppy_input_without_microchip(self):
        """Test PuppyInput with optional microchip field."""
        from app.schemas.breeding import PuppyInput
        
        puppy = PuppyInput(
            name="Max",
            gender="Male",
            birth_date=date(2024, 1, 15)
        )
        assert puppy.microchip is None
    
    def test_puppy_batch_with_valid_data(self):
        """Test PuppyBatch with multiple puppies."""
        from app.schemas.breeding import PuppyBatch, PuppyInput
        
        puppies_data = {
            "puppies": [
                {
                    "name": "Max",
                    "gender": "Male",
                    "birth_date": date(2024, 1, 15)
                },
                {
                    "name": "Bella",
                    "gender": "Female",
                    "birth_date": date(2024, 1, 15)
                }
            ]
        }
        batch = PuppyBatch(**puppies_data)
        assert len(batch.puppies) == 2
        assert batch.puppies[0].name == "Max"
        assert batch.puppies[1].name == "Bella"
    
    def test_puppy_batch_with_empty_list(self):
        """Test PuppyBatch rejects empty puppy list."""
        from app.schemas.breeding import PuppyBatch
        
        with pytest.raises(ValidationError) as exc_info:
            PuppyBatch(puppies=[])
        
        errors = exc_info.value.errors()
        assert any("at least 1 item" in str(error["msg"]).lower() for error in errors)
    
    def test_litter_response_serialization(self):
        """Test LitterResponse schema serialization."""
        from app.schemas.breeding import LitterResponse, LitterStatus
        
        response_data = {
            "id": 1,
            "description": "Test breeding",
            "status": LitterStatus.STARTED,
            "created_at": datetime.now(),
            "updated_at": None,
            "parent_pets": None,
            "puppies": None
        }
        response = LitterResponse(**response_data)
        assert response.id == 1
        assert response.status == LitterStatus.STARTED
        assert response.description == "Test breeding"
    
    def test_litter_response_with_parent_pets(self):
        """Test LitterResponse with parent pets data."""
        from app.schemas.breeding import LitterResponse, LitterStatus
        
        response_data = {
            "id": 1,
            "description": "Test breeding",
            "status": LitterStatus.IN_PROCESS,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "parent_pets": [
                {"id": str(uuid.uuid4()), "name": "Max", "breed": "Labrador"},
                {"id": str(uuid.uuid4()), "name": "Bella", "breed": "Labrador"}
            ],
            "puppies": None
        }
        response = LitterResponse(**response_data)
        assert len(response.parent_pets) == 2
        assert response.status == LitterStatus.IN_PROCESS
    
    def test_litter_response_with_puppies(self):
        """Test LitterResponse with puppies data."""
        from app.schemas.breeding import LitterResponse, LitterStatus
        
        response_data = {
            "id": 1,
            "description": "Test breeding",
            "status": LitterStatus.DONE,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "parent_pets": [
                {"id": str(uuid.uuid4()), "name": "Max", "breed": "Labrador"},
                {"id": str(uuid.uuid4()), "name": "Bella", "breed": "Labrador"}
            ],
            "puppies": [
                {"id": str(uuid.uuid4()), "name": "Puppy1", "gender": "Male"},
                {"id": str(uuid.uuid4()), "name": "Puppy2", "gender": "Female"}
            ]
        }
        response = LitterResponse(**response_data)
        assert len(response.puppies) == 2
        assert response.status == LitterStatus.DONE
    
    def test_litter_status_enum_values(self):
        """Test LitterStatus enum has correct values."""
        from app.schemas.breeding import LitterStatus
        
        assert LitterStatus.STARTED.value == "Started"
        assert LitterStatus.IN_PROCESS.value == "InProcess"
        assert LitterStatus.DONE.value == "Done"
        assert LitterStatus.VOIDED.value == "Voided"


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
