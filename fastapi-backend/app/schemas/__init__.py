"""Pydantic schemas for request/response validation."""
from app.schemas.user import (
    UserRead,
    UserCreate,
    UserUpdate,
    PetSeekerCreate,
    GuestToAccountCreate,
)
from app.schemas.pet import PetBase, PetCreate, PetUpdate, PetRead
from app.schemas.breed import (
    BreedBase,
    BreedCreate,
    BreedUpdate,
    BreedRead,
    BreedColourBase,
    BreedColourCreate,
    BreedColourUpdate,
    BreedColourRead,
)
from app.schemas.breeding import LitterBase, LitterCreate, LitterUpdate, LitterRead
from app.schemas.location import LocationBase, LocationCreate, LocationUpdate, LocationRead
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageListItem,
    MessageListResponse,
    MessageUpdate,
    MessageResponseCreate,
    UnreadCountResponse,
    MessageSendResponse,
)
from app.schemas.offspring import OffspringBase, OffspringCreate, OffspringUpdate, OffspringRead
from app.schemas.offspring_image import OffspringImageRead
from app.schemas.offspring_favorite import OffspringFavoriteRead
from app.schemas.notification import NotificationRead

# Rebuild models to resolve forward references
OffspringRead.model_rebuild()

__all__ = [
    # User schemas
    "UserRead",
    "UserCreate",
    "UserUpdate",
    "PetSeekerCreate",
    "GuestToAccountCreate",
    # Pet schemas
    "PetBase",
    "PetCreate",
    "PetUpdate",
    "PetRead",
    # Breed schemas
    "BreedBase",
    "BreedCreate",
    "BreedUpdate",
    "BreedRead",
    "BreedColourBase",
    "BreedColourCreate",
    "BreedColourUpdate",
    "BreedColourRead",
    # Breeding schemas
    "LitterBase",
    "LitterCreate",
    "LitterUpdate",
    "LitterRead",
    # Location schemas
    "LocationBase",
    "LocationCreate",
    "LocationUpdate",
    "LocationRead",
    # Message schemas
    "MessageCreate",
    "MessageResponse",
    "MessageListItem",
    "MessageListResponse",
    "MessageUpdate",
    "MessageResponseCreate",
    "UnreadCountResponse",
    "MessageSendResponse",
    # Offspring schemas
    "OffspringBase",
    "OffspringCreate",
    "OffspringUpdate",
    "OffspringRead",
    # Offspring image schemas
    "OffspringImageRead",
    # Offspring favorite schemas
    "OffspringFavoriteRead",
    # Notification schemas
    "NotificationRead",
]
