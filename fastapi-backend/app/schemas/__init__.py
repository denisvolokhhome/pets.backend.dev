"""Pydantic schemas for request/response validation."""
from app.schemas.user import UserRead, UserCreate, UserUpdate
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

__all__ = [
    # User schemas
    "UserRead",
    "UserCreate",
    "UserUpdate",
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
]
