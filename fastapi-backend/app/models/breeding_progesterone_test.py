"""A progesterone test result logged for a breeding (planner)."""
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding


class BreedingProgesteroneTest(Base):
    __tablename__ = "breeding_progesterone_tests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breeding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tested_on: Mapped[date] = mapped_column(Date, nullable=False)
    value_ng_ml: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    breeding: Mapped["Breeding"] = relationship("Breeding", back_populates="progesterone_tests")
