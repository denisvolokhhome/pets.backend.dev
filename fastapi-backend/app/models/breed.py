"""Breed and BreedColour models for managing dog and cat breeds."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Breed(Base):
    """
    Breed model representing a dog or cat breed.
    """
    __tablename__ = "breeds"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True
    )  # "dog" or "cat"

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

    # Relationships. pets/offsprings are lazy="select": "selectin" made every breed list
    # (and every Pet/Offspring .breed) load all pets and offspring of those breeds.
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="breed",
        lazy="select"
    )
    colours: Mapped[list["BreedColour"]] = relationship(
        "BreedColour",
        back_populates="breed",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    offsprings: Mapped[list["Offspring"]] = relationship(
        "Offspring",
        back_populates="breed",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Breed(id={self.id}, name={self.name}, kind={self.kind})>"


class BreedColour(Base):
    """
    BreedColour model representing available colors for a breed.

    Many-to-one relationship with Breed.
    """
    __tablename__ = "breed_colours"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    breed_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("breeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True
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

    # Relationships. pets/offsprings are lazy="select": "selectin" made every breed list
    # (and every Pet/Offspring .breed) load all pets and offspring of those breeds.
    breed: Mapped["Breed"] = relationship(
        "Breed",
        back_populates="colours",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<BreedColour(id={self.id}, name={self.name}, breed_id={self.breed_id})>"