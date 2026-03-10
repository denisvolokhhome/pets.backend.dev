"""Schemas for pet image operations."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


class PetImageBase(BaseModel):
    """Base schema for pet image data."""
    image_path: str
    image_file_name: str
    display_order: int = 0
    is_primary: bool = False


class PetImageCreate(PetImageBase):
    """Schema for creating a pet image."""
    pet_id: uuid.UUID


class PetImageRead(PetImageBase):
    """Schema for reading pet image data."""
    id: int
    pet_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @computed_field
    @property
    def image_url(self) -> str:
        """Compute the full image URL from the image path."""
        # Format: /storage/{image_path}
        return f"/storage/{self.image_path}"

    model_config = ConfigDict(from_attributes=True)


class PetImageUpdate(BaseModel):
    """Schema for updating pet image."""
    display_order: Optional[int] = None
    is_primary: Optional[bool] = None
