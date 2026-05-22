"""ServiceCategory model and user_service_categories association table."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


# Association table: many-to-many between users and service categories
user_service_categories = Table(
    "user_service_categories",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Integer,
        ForeignKey("service_categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    UniqueConstraint("user_id", "category_id", name="uq_user_service_category"),
)


class ServiceCategory(Base):
    """
    ServiceCategory model representing a predefined classification of pet services.

    Examples: Grooming, Dog Walking, Cat Sitting, Pet Training, etc.
    """
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    icon: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Back-reference to users who offer this category
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_service_categories",
        back_populates="service_categories",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ServiceCategory(id={self.id}, slug={self.slug})>"
