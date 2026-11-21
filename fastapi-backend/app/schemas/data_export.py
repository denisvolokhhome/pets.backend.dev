"""Schemas for breeder data exports."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DataExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    file_size: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_expired: bool = False


class DownloadLink(BaseModel):
    # Path relative to the API host; the client prefixes its API host
    url: str
