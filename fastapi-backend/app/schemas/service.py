"""Service schemas for API request/response validation."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.service_category import ServiceCategoryRead


class ServiceCreate(BaseModel):
    """Schema for creating a new service listing."""
    category_id: int
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    price_from: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_to: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_unit: Optional[str] = Field(
        None,
        pattern="^(per_session|per_hour|per_day|per_visit)$",
    )
    location_ids: List[int] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_price_range(self) -> "ServiceCreate":
        """Enforce price_from <= price_to when both are provided."""
        if self.price_from is not None and self.price_to is not None:
            if self.price_from > self.price_to:
                raise ValueError("price_from must be <= price_to")
        return self


class ServiceUpdate(BaseModel):
    """Schema for updating an existing service listing (all fields optional)."""
    category_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    price_from: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_to: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_unit: Optional[str] = Field(
        None,
        pattern="^(per_session|per_hour|per_day|per_visit)$",
    )
    location_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_price_range(self) -> "ServiceUpdate":
        """Enforce price_from <= price_to when both are provided."""
        if self.price_from is not None and self.price_to is not None:
            if self.price_from > self.price_to:
                raise ValueError("price_from must be <= price_to")
        return self


class ServiceImageRead(BaseModel):
    """Schema for reading service image data."""
    id: uuid.UUID
    service_id: uuid.UUID
    image_path: str
    is_primary: bool
    display_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceRead(BaseModel):
    """Schema for reading a service with all related data."""
    id: uuid.UUID
    user_id: uuid.UUID
    category_id: int
    title: str
    description: Optional[str] = None
    price_from: Optional[Decimal] = None
    price_to: Optional[Decimal] = None
    price_unit: Optional[str] = None
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Embedded from the category relationship — no extra API call needed
    category_name: str = ""
    category_slug: str = ""

    # Image relationships
    images: List[ServiceImageRead] = []
    primary_image: Optional[ServiceImageRead] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_category_fields(cls, data: Any) -> Any:
        """
        Populate category_name and category_slug from the nested category
        relationship when constructing from an ORM object.

        Works for both ORM instances (has a .category attribute) and plain
        dicts (already have category_name / category_slug keys).
        """
        # ORM object path: data has a .category attribute
        if hasattr(data, "category") and data.category is not None:
            # Use object.__setattr__ to avoid triggering Pydantic validation
            # before the model is fully constructed — we just mutate the raw
            # object so the subsequent field extraction picks up the values.
            # Since we're in mode="before", data is still the raw input; we
            # convert it to a dict-like structure via model_fields approach.
            # The cleanest approach: return a dict built from the ORM object.
            category = data.category
            return {
                "id": data.id,
                "user_id": data.user_id,
                "category_id": data.category_id,
                "title": data.title,
                "description": data.description,
                "price_from": data.price_from,
                "price_to": data.price_to,
                "price_unit": data.price_unit,
                "is_active": data.is_active,
                "is_deleted": data.is_deleted,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "category_name": category.name,
                "category_slug": category.slug,
                "images": list(data.images) if data.images else [],
                "primary_image": next(
                    (img for img in data.images if img.is_primary), None
                ) if data.images else None,
            }

        # Dict path: already has the fields (e.g. from model_dump / test data)
        return data


class ServiceListResponse(BaseModel):
    """Schema for paginated service list response."""
    items: List[ServiceRead]
    total: int
    page: int
    page_size: int


class ServiceSearchResult(BaseModel):
    """Public search result for a service provider."""
    user_id: uuid.UUID
    provider_name: str
    service_description: Optional[str] = None
    profile_image_url: Optional[str] = None
    categories: List[ServiceCategoryRead]
    distance_km: Optional[float] = None
    active_services_count: int

    model_config = ConfigDict(from_attributes=True)


class PublicProviderProfile(BaseModel):
    """Full public profile for a service provider."""
    user_id: uuid.UUID
    provider_name: str
    service_description: Optional[str] = None
    profile_image_url: Optional[str] = None
    categories: List[ServiceCategoryRead]
    services: List[ServiceRead]
    locations: List[dict]  # Simplified location data

    model_config = ConfigDict(from_attributes=True)
