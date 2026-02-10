"""Pydantic schemas for geocoding service."""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class Coordinates(BaseModel):
    """Geographic coordinates."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "latitude": 40.7128,
                "longitude": -74.0060
            }
        }
    )
    
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")


class Address(BaseModel):
    """Address information from reverse geocoding."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "zip_code": "10001",
                "city": "New York",
                "state": "New York",
                "country": "United States"
            }
        }
    )
    
    zip_code: Optional[str] = Field(None, description="Postal/ZIP code")
    city: Optional[str] = Field(None, description="City name")
    state: Optional[str] = Field(None, description="State/province name")
    country: Optional[str] = Field(None, description="Country name")

