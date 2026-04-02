"""Plan model for subscription plan management."""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Integer, Numeric, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Plan(Base):
    """
    Plan model representing a subscription tier with usage limits and pricing.

    Each plan defines the resource caps (pets, locations, offsprings) and billing
    details (price, currency, interval) for a breeder subscription.
    """
    __tablename__ = "plans"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # Plan details
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="usd"
    )

    billing_interval: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="month"
    )

    # Usage limits
    max_pets: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    max_published_locations: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    max_simultaneous_offsprings: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    # Default plan flag
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
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

    def __repr__(self) -> str:
        try:
            id_val = object.__getattribute__(self, 'id')
            name_val = object.__getattribute__(self, 'name')
            return f"<Plan(id={id_val}, name={name_val})>"
        except AttributeError:
            return f"<Plan(detached)>"
