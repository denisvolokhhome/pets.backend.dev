"""Litter model for managing groups of puppies."""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Litter(Base):
    """
    Litter model representing a group of puppies born together.
    
    One-to-many relationship with Pet (multiple pets can belong to one litter).
    Uses integer primary key to match Laravel schema.
    """
    __tablename__ = "litters"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Litter information
    date_of_litter: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
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
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="litter",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Litter(id={self.id}, date_of_litter={self.date_of_litter})>"
