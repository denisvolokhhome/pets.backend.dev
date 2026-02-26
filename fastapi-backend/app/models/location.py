"""Location model for managing breeder locations."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape, from_shape
from shapely.geometry import Point

from app.database import Base


class Location(Base):
    """
    Location model representing a physical location for a breeder.
    
    Associated with a user and can be linked to pets.
    Uses integer primary key to match Laravel schema.
    Includes PostGIS geometry column for efficient geospatial queries.
    """
    __tablename__ = "locations"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign key to user
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Location information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    address1: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    address2: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    city: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    country: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    zipcode: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    location_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: user or pet"
    )
    is_published: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default='true'
    )
    
    # Geospatial columns
    latitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    coordinates: Mapped[Optional[Point]] = mapped_column(
        Geometry(geometry_type='POINT', srid=4326),
        nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="locations",
        lazy="selectin"
    )
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="location",
        lazy="selectin"
    )
    
    # Helper properties for accessing coordinates from geometry column
    @property
    def lat(self) -> Optional[float]:
        """Get latitude from geometry column or latitude field."""
        if self.coordinates:
            point = to_shape(self.coordinates)
            return point.y
        return self.latitude
    
    @property
    def lon(self) -> Optional[float]:
        """Get longitude from geometry column or longitude field."""
        if self.coordinates:
            point = to_shape(self.coordinates)
            return point.x
        return self.longitude
    
    def set_coordinates(self, latitude: float, longitude: float) -> None:
        """
        Set coordinates from lat/lon values.
        
        Updates both the geometry column (for spatial queries) and
        the latitude/longitude columns (for backward compatibility).
        
        Args:
            latitude: Latitude value (-90 to 90)
            longitude: Longitude value (-180 to 180)
        """
        # Update lat/lon columns
        self.latitude = latitude
        self.longitude = longitude
        
        # Update geometry column
        point = Point(longitude, latitude)
        self.coordinates = from_shape(point, srid=4326)
    
    def get_coordinates_tuple(self) -> Optional[tuple[float, float]]:
        """
        Get coordinates as a tuple (latitude, longitude).
        
        Returns:
            Tuple of (latitude, longitude) or None if coordinates not set
        """
        if self.coordinates:
            point = to_shape(self.coordinates)
            return (point.y, point.x)
        elif self.latitude is not None and self.longitude is not None:
            return (self.latitude, self.longitude)
        return None
    
    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name={self.name}, user_id={self.user_id}, lat={self.lat}, lon={self.lon})>"
