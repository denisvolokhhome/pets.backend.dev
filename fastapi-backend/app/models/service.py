"""Service, ServiceImage models and service_locations association table."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer,
    Numeric, String, Table, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.service_category import ServiceCategory
    from app.models.location import Location


# Association table: many-to-many between services and locations
service_locations = Table(
    "service_locations",
    Base.metadata,
    Column(
        "service_id",
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "location_id",
        Integer,
        ForeignKey("locations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Service(Base):
    """
    Service model representing an individual service listing by a service provider.

    Supports optional pricing, multiple locations, and soft deletion.
    """
    __tablename__ = "services"

    __table_args__ = (
        CheckConstraint(
            "price_unit IN ('per_session', 'per_hour', 'per_day', 'per_visit') OR price_unit IS NULL",
            name="ck_services_price_unit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_categories.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    price_from: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    price_to: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    price_unit: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="per_session | per_hour | per_day | per_visit",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )
    category: Mapped["ServiceCategory"] = relationship(
        "ServiceCategory",
        lazy="selectin",
    )
    locations: Mapped[list["Location"]] = relationship(
        "Location",
        secondary="service_locations",
        lazy="selectin",
    )
    images: Mapped[list["ServiceImage"]] = relationship(
        "ServiceImage",
        back_populates="service",
        order_by="ServiceImage.display_order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, title={self.title!r}, user_id={self.user_id})>"


class ServiceImage(Base):
    """
    ServiceImage model for storing multiple images per service.

    Mirrors the offspring_images pattern: supports primary image designation
    and custom display ordering.
    """
    __tablename__ = "service_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship back to service
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="images",
    )

    def __repr__(self) -> str:
        return (
            f"<ServiceImage(id={self.id}, service_id={self.service_id}, "
            f"is_primary={self.is_primary})>"
        )
