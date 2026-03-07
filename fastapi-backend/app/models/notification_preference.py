"""Notification preference model for user notification settings."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class NotificationPreference(Base):
    """Model for user notification preferences."""
    
    __tablename__ = "notification_preferences"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Notification type preferences
    message_received = Column(Boolean, default=True, nullable=False)
    favorite_added = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="notification_preferences")
    
    def __repr__(self) -> str:
        return f"<NotificationPreference(user_id={self.user_id}, message={self.message_received}, favorite={self.favorite_added})>"
