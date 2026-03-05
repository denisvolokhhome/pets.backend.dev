"""Offspring favorite schemas for API request/response validation."""
from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.schemas.offspring import OffspringRead


class OffspringFavoriteRead(BaseModel):
    """Schema for reading offspring favorite data."""
    id: uuid.UUID
    offspring_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    
    # Nested offspring relationship
    offspring: "OffspringRead"
    
    model_config = ConfigDict(from_attributes=True)
