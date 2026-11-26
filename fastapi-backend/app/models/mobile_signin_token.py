"""One-time QR codes that sign a desktop user in on their phone ("instant mobile switch")."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MobileSigninToken(Base):
    """
    Only the SHA-256 of the code is stored; the raw code exists in the QR alone.
    A code is single use (``used_at``) and short-lived (``expires_at``). ``acknowledged_at``
    marks "the phone was already signed in as this user" (code left unused).
    """
    __tablename__ = "mobile_signin_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # App page to open on the phone (validated relative path)
    target_path: Mapped[str] = mapped_column(String(500), nullable=False, default="/dashboard")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Small support record of the redemption (hashed IP, browser)
    used_ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    used_user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User")
