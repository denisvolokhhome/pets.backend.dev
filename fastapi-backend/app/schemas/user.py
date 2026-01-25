"""User schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi_users import schemas
from pydantic import BaseModel


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Schema for reading user data."""
    id: uuid.UUID
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Profile fields
    breedery_name: Optional[str] = None
    profile_image_path: Optional[str] = None
    breedery_description: Optional[str] = None
    search_tags: Optional[List[str]] = None


class UserCreate(schemas.BaseUserCreate):
    """Schema for creating a new user."""
    email: str
    password: str


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user data."""
    password: Optional[str] = None
    email: Optional[str] = None
    
    # Profile fields
    breedery_name: Optional[str] = None
    breedery_description: Optional[str] = None
    search_tags: Optional[List[str]] = None


class ProfileImageResponse(BaseModel):
    """Schema for profile image upload response."""
    profile_image_path: str
    message: str
