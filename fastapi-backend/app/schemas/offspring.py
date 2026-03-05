"""Offspring schemas for API request/response validation."""
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from app.schemas.breeding import LitterRead
    from app.schemas.breed import BreedRead
    from app.schemas.offspring_image import OffspringImageRead
    from app.schemas.pet import PetRead


class OffspringBase(BaseModel):
    """Base schema for offspring data."""
    name: Optional[str] = Field(None, max_length=255)
    gender: str = Field(..., pattern="^(Male|Female)$")
    date_of_birth: date
    status: str = Field(
        default="Available",
        pattern="^(Available|Reserved|Sold|Archived)$"
    )
    price: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    color_markings: Optional[str] = None
    
    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v: date) -> date:
        """Ensure date of birth is not in the future."""
        if v > date.today():
            raise ValueError('Date of birth cannot be in the future')
        return v
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure price is non-negative."""
        if v is not None and v < 0:
            raise ValueError('Price must be non-negative')
        return v


class OffspringCreate(OffspringBase):
    """Schema for creating a new offspring."""
    breeding_id: int
    
    # breed_id is auto-populated from breeding
    # user_id is auto-populated from authenticated user


class OffspringUpdate(BaseModel):
    """Schema for updating an offspring."""
    name: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(
        None,
        pattern="^(Available|Reserved|Sold|Archived)$"
    )
    price: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    color_markings: Optional[str] = None
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure price is non-negative."""
        if v is not None and v < 0:
            raise ValueError('Price must be non-negative')
        return v
    
    # breeding_id, gender, date_of_birth are immutable after creation


class OffspringRead(OffspringBase):
    """Schema for reading offspring data with relationships."""
    id: uuid.UUID
    breeding_id: int
    user_id: uuid.UUID
    breed_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Computed fields
    age: str
    favorites_count: int
    messages_count: int
    
    # Relationships (will be populated by service layer)
    breeding: Optional["LitterRead"] = None
    breed: Optional["BreedRead"] = None
    images: List["OffspringImageRead"] = []
    primary_image: Optional["OffspringImageRead"] = None
    father: Optional["PetRead"] = None
    mother: Optional["PetRead"] = None
    
    model_config = ConfigDict(from_attributes=True)
