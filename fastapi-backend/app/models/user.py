"""User model for authentication and user management."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String, Boolean, DateTime, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """
    User model extending fastapi-users base user table.
    
    Uses UUID primary key for compatibility with Laravel system.
    Includes standard fastapi-users fields plus custom fields.
    """
    __tablename__ = "users"
    
    # Override id to ensure UUID type
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # fastapi-users required fields (inherited but explicitly defined for clarity)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # Additional fields from Laravel
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    remember_token: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    
    # Profile fields for breedery information
    breedery_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    profile_image_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    breedery_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    search_tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
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
    
    # Relationships (forward references to avoid circular imports)
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="user",
        lazy="selectin"
    )
    locations: Mapped[list["Location"]] = relationship(
        "Location",
        back_populates="user",
        lazy="selectin"
    )
    contacts: Mapped[list["UserContact"]] = relationship(
        "UserContact",
        back_populates="user",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
