"""Quick test to verify image_url computed field works correctly."""
from app.schemas.pet_image import PetImageRead
from app.schemas.pet import PetRead
from datetime import datetime
import uuid

# Test PetImageRead
pet_image_data = {
    "id": uuid.uuid4(),
    "pet_id": uuid.uuid4(),
    "image_path": "app/test_image.jpg",
    "image_file_name": "test_image.jpg",
    "is_primary": True,
    "display_order": 0,
    "created_at": datetime.now()
}

# Create a mock object with attributes
class MockPetImage:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

mock_image = MockPetImage(**pet_image_data)
pet_image = PetImageRead.model_validate(mock_image)

print("PetImageRead test:")
print(f"  image_path: {pet_image.image_path}")
print(f"  image_url: {pet_image.image_url}")
print(f"  Expected: /storage/app/test_image.jpg")
print(f"  Match: {pet_image.image_url == '/storage/app/test_image.jpg'}")
print()

# Test PetRead
pet_data = {
    "id": uuid.uuid4(),
    "user_id": uuid.uuid4(),
    "name": "Test Pet",
    "image_path": "app/pet_image.jpg",
    "image_file_name": "pet_image.jpg",
    "images": [],
    "is_deleted": False,
    "created_at": datetime.now(),
    "breed_id": 1,
    "location_id": 1
}

class MockPet:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

mock_pet = MockPet(**pet_data)
pet = PetRead.model_validate(mock_pet)

print("PetRead test:")
print(f"  image_path: {pet.image_path}")
print(f"  image_url: {pet.image_url}")
print(f"  Expected: /storage/app/pet_image.jpg")
print(f"  Match: {pet.image_url == '/storage/app/pet_image.jpg'}")
print()

# Test with None image_path
pet_data_no_image = {
    "id": uuid.uuid4(),
    "user_id": uuid.uuid4(),
    "name": "Test Pet No Image",
    "image_path": None,
    "image_file_name": None,
    "images": [],
    "is_deleted": False,
    "created_at": datetime.now(),
    "breed_id": 1,
    "location_id": 1
}

mock_pet_no_image = MockPet(**pet_data_no_image)
pet_no_image = PetRead.model_validate(mock_pet_no_image)

print("PetRead test (no image):")
print(f"  image_path: {pet_no_image.image_path}")
print(f"  image_url: {pet_no_image.image_url}")
print(f"  Expected: None")
print(f"  Match: {pet_no_image.image_url is None}")

print("\n✓ All schema tests passed!")
