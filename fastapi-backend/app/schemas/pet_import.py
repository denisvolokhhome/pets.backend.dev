"""Pet import schemas for CSV bulk import request/response validation."""
from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class PetImportRow(BaseModel):
    """Single row from CSV import — uses name strings for breed/location."""
    row_number: int
    name: str = Field(..., min_length=1, max_length=255)

    @field_validator('name')
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Name cannot be empty or whitespace-only')
        return v

    breed: Optional[str] = Field(None, max_length=255)
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight: Optional[float] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=10000)
    location: Optional[str] = Field(None, max_length=255)
    microchip: Optional[str] = Field(None, max_length=255)
    vaccination: Optional[str] = Field(None, max_length=10000)
    health_certificate: Optional[str] = Field(None, max_length=10000)
    deworming: Optional[str] = Field(None, max_length=10000)
    birth_certificate: Optional[str] = Field(None, max_length=10000)

    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v: Optional[str]) -> Optional[str]:
        """Validate gender is Male or Female (case-insensitive), normalize to title case."""
        if v is None:
            return v
        normalized = v.strip().lower()
        if normalized not in ('male', 'female'):
            raise ValueError('Gender must be Male or Female')
        return normalized.title()


class ImportPayload(BaseModel):
    """Request body for POST /api/pets/import."""
    pets: List[PetImportRow]

    @field_validator('pets')
    @classmethod
    def validate_pets_count(cls, v: List[PetImportRow]) -> List[PetImportRow]:
        """Enforce min 1 and max 500 rows."""
        if len(v) == 0:
            raise ValueError('At least one pet is required')
        if len(v) > 500:
            raise ValueError('Maximum 500 pets per import')
        return v


class ImportError(BaseModel):
    """A single row-level error."""
    row: int
    reason: str


class ImportResult(BaseModel):
    """Response from the import endpoint."""
    created_count: int
    skipped_count: int
    errors: List[ImportError]
    plan_limit_applied: bool
