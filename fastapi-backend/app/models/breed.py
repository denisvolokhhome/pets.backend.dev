"""Breed and BreedColour models for managing dog breeds."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Breed(Base):
    """
    Breed model representing a dog breed.
    
    Includes breed classification and associated colors.
    Uses integer primary key to match Laravel schema.
    """
    __tablename__ = "breeds"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Breed information
    code: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    group: Mapped[Optional[str]] = mapped_column(
        Text,
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
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="breed",
        lazy="selectin"
    )
    colours: Mapped[list["BreedColour"]] = relationship(
        "BreedColour",
        back_populates="breed",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Breed(id={self.id}, name={self.name})>"


class BreedColour(Base):
    """
    BreedColour model representing available colors for a breed.
    
    Many-to-one relationship with Breed.
    Uses integer primary key to match Laravel schema.
    """
    __tablename__ = "breed_colours"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign key
    breed_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("breeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Color information
    code: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
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
    breed: Mapped["Breed"] = relationship(
        "Breed",
        back_populates="colours",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<BreedColour(id={self.id}, name={self.name}, breed_id={self.breed_id})>"
