"""Schemas for breeder search functionality."""
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from uuid import UUID


class BreedInfo(BaseModel):
    """Information about a breed available at a breeding location."""
    
    breed_id: int = Field(..., description="Unique identifier for the breed")
    breed_name: str = Field(..., description="Name of the breed")
    pet_count: int = Field(..., ge=0, description="Number of pets of this breed at this location")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "breed_id": 1,
                "breed_name": "Golden Retriever",
                "pet_count": 3
            }
        }


class BreederSearchResult(BaseModel):
    """Result object for breeding location search."""
    
    location_id: int = Field(..., description="Unique identifier for the breeding location")
    user_id: UUID = Field(..., description="Unique identifier for the breeder/user")
    breeder_name: str = Field(..., description="Name of the breeder or breedery")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude of the breeding location")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude of the breeding location")
    distance: float = Field(..., ge=0, description="Distance from search center in miles")
    available_breeds: List[BreedInfo] = Field(
        default_factory=list,
        description="List of breeds available at this location"
    )
    thumbnail_url: Optional[str] = Field(None, description="URL to breeder profile image or representative pet image")
    location_description: Optional[str] = Field(None, description="Description or name of the breeding location")
    rating: Optional[float] = Field(None, ge=0, le=5, description="Breeder rating (future feature)")
    
    @validator('distance')
    def round_distance(cls, v):
        """Round distance to 1 decimal place."""
        return round(v, 1)
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "location_id": 1,
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "breeder_name": "Happy Paws Kennel",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "distance": 5.3,
                "available_breeds": [
                    {
                        "breed_id": 1,
                        "breed_name": "Golden Retriever",
                        "pet_count": 3
                    },
                    {
                        "breed_id": 2,
                        "breed_name": "Labrador Retriever",
                        "pet_count": 2
                    }
                ],
                "thumbnail_url": "/storage/profile_image.jpg",
                "location_description": "Main Breeding Facility",
                "rating": None
            }
        }
