"""ServiceCategory schemas for API request/response validation."""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ServiceCategoryRead(BaseModel):
    """Schema for reading service category data."""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
