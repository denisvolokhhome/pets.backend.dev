"""Offspring image schemas for API request/response validation."""
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, computed_field


class OffspringImageRead(BaseModel):
    """Schema for reading offspring image data."""
    id: uuid.UUID
    offspring_id: uuid.UUID
    image_path: str
    is_primary: bool
    display_order: int
    created_at: datetime
    
    @computed_field
    @property
    def image_url(self) -> str:
        """Compute the full image URL from the image path."""
        # Assuming the storage URL pattern matches the existing file service
        # Format: /storage/{image_path}
        return f"/storage/{self.image_path}"
    
    model_config = ConfigDict(from_attributes=True)
