"""User schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List, Literal, Any

from fastapi_users import schemas
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ServiceCategoryBrief(BaseModel):
    """Minimal service category info embedded in UserRead."""
    id: int
    name: str
    slug: str
    model_config = ConfigDict(from_attributes=True)


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Schema for reading user data."""
    id: uuid.UUID
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    is_breeder: bool
    account_type: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Profile fields
    name: Optional[str] = None
    phone_number: Optional[str] = None
    oauth_provider: Optional[str] = None
    breedery_name: Optional[str] = None
    profile_image_path: Optional[str] = None
    breedery_description: Optional[str] = None
    search_tags: Optional[List[str]] = None

    # Service provider categories
    service_categories: Optional[List[ServiceCategoryBrief]] = None

    model_config = {"from_attributes": True}


class UserCreate(schemas.BaseUserCreate):
    """Schema for creating a new user."""
    email: str
    password: str
    is_breeder: bool = True  # Default to breeder for backward compatibility


class PetSeekerCreate(BaseModel):
    """Simplified schema for pet seeker registration."""
    email: str
    password: str
    name: Optional[str] = None


class GuestToAccountCreate(BaseModel):
    """Schema for converting guest message sender to account."""
    email: str  # Pre-filled from message
    password: str
    name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user data."""
    password: Optional[str] = None
    email: Optional[str] = None
    
    # Profile fields
    name: Optional[str] = None
    phone_number: Optional[str] = None
    breedery_name: Optional[str] = None
    breedery_description: Optional[str] = None
    search_tags: Optional[List[str]] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Strip whitespace
        v = v.strip()
        if not v:
            return None
        # Must look like a phone number (digits, spaces, dashes, parens, plus)
        import re
        if not re.match(r"^[\d\s\-\(\)\+\.]+$", v):
            raise ValueError("Invalid phone number format")
        if len(v) > 50:
            raise ValueError("Phone number too long")
        return v


class ServiceProviderCreate(BaseModel):
    """Schema for registering a new service provider account."""
    email: str
    password: str
    name: Optional[str] = None
    account_type: Literal["service"] = "service"
    category_ids: List[int] = Field(..., min_length=1)


class ProfileImageResponse(BaseModel):
    """Schema for profile image upload response."""
    profile_image_path: str
    message: str
