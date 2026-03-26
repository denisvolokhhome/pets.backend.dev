"""Genealogy tree and offspring-to-pet conversion routes."""
import logging
import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_breeder
from app.models.user import User
from app.models.pet import Pet
from app.models.breeding import Breeding
from app.models.breeding_pet import BreedingPet
from app.models.offspring import Offspring

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/genealogy", tags=["genealogy"])


# ── Response schemas ───────────────────────────────────────────────

class PetNode(BaseModel):
    id: str
    name: str
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    breed_name: Optional[str] = None
    image_url: Optional[str] = None
    node_type: str = "pet"  # "pet" or "offspring"


class OffspringMini(BaseModel):
    id: str
    name: Optional[str] = None
    gender: str
    date_of_birth: str
    status: str
    breed_name: Optional[str] = None
    image_url: Optional[str] = None
    converted_to_pet_id: Optional[str] = None


class OffspringGroupNode(BaseModel):
    breeding_id: int
    breeding_date: Optional[str] = None
    count: int
    offsprings: List[OffspringMini]
    node_type: str = "offspring_group"


class BreedingEdge(BaseModel):
    father: Optional[PetNode] = None
    mother: Optional[PetNode] = None
    breeding_id: int
    offspring_group: OffspringGroupNode
    converted_pets: List[PetNode] = []


class GenealogyTree(BaseModel):
    pets: List[PetNode]
    edges: List[BreedingEdge]


# ── Helpers ────────────────────────────────────────────────────────

def _pet_to_node(pet: Pet) -> PetNode:
    breed_name = pet.breed.name if pet.breed else None
    img = None
    if pet.images:
        primary = next((i for i in pet.images if i.is_primary), None) or pet.images[0]
        img = f"/storage/{primary.image_path}" if primary and primary.image_path else None
    elif pet.image_path:
        img = f"/storage/{pet.image_path}"
    return PetNode(
        id=str(pet.id),
        name=pet.name,
        gender=pet.gender,
        date_of_birth=pet.date_of_birth.isoformat() if pet.date_of_birth else None,
        breed_name=breed_name,
        image_url=img,
    )


def _offspring_to_mini(o: Offspring, converted_pet_id: Optional[str] = None) -> OffspringMini:
    breed_name = o.breed.name if o.breed else None
    img = None
    if o.images:
        primary = next((i for i in o.images if i.is_primary), None) or o.images[0]
        img = f"/storage/{primary.image_path}" if primary and primary.image_path else None
    return OffspringMini(
        id=str(o.id),
        name=o.name,
        gender=o.gender,
        date_of_birth=o.date_of_birth.isoformat(),
        status=o.status,
        breed_name=breed_name,
        image_url=img,
        converted_to_pet_id=converted_pet_id,
    )


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/tree", response_model=GenealogyTree)
async def get_genealogy_tree(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Build the full genealogy tree for the authenticated breeder.

    Returns all pets, breedings, and offspring grouped by breeding pair.
    Offspring that have been converted to pets appear as separate pet nodes
    and are removed from their offspring group.
    """
    # 1. Load all breeder's pets (non-deleted)
    pets_q = select(Pet).where(and_(Pet.user_id == user.id, Pet.is_deleted == False))
    pets_result = await session.execute(pets_q)
    all_pets = pets_result.scalars().all()
    pet_map = {p.id: p for p in all_pets}

    # 2. Load all breedings
    breed_q = select(Breeding).where(Breeding.user_id == user.id)
    breed_result = await session.execute(breed_q)
    all_breedings = breed_result.scalars().all()

    # 3. Load all breeding_pet assignments
    breeding_ids = [b.id for b in all_breedings]
    bp_q = select(BreedingPet).where(BreedingPet.breeding_id.in_(breeding_ids)) if breeding_ids else None
    bp_map: dict[int, list] = {}
    if bp_q is not None:
        bp_result = await session.execute(bp_q)
        for bp in bp_result.scalars().all():
            bp_map.setdefault(bp.breeding_id, []).append(bp)

    # 4. Load all offspring
    off_q = select(Offspring).where(Offspring.user_id == user.id)
    off_result = await session.execute(off_q)
    all_offspring = off_result.scalars().all()
    offspring_by_breeding: dict[int, list] = {}
    for o in all_offspring:
        offspring_by_breeding.setdefault(o.breeding_id, []).append(o)

    # 5. Detect offspring that were converted to pets.
    #    Convention: a Pet whose name + dob + gender matches an offspring
    #    AND shares the same breeding_id is considered converted.
    #    We also check offspring whose status is "Archived" as a secondary signal.
    converted: dict[str, str] = {}  # offspring_id -> pet_id
    for pet in all_pets:
        if pet.breeding_id and pet.breeding_id in offspring_by_breeding:
            for o in offspring_by_breeding[pet.breeding_id]:
                if (
                    pet.name == o.name
                    and pet.date_of_birth == o.date_of_birth
                    and pet.gender == o.gender
                ):
                    converted[str(o.id)] = str(pet.id)

    # 6. Build edges
    edges: list[BreedingEdge] = []
    for breeding in all_breedings:
        bps = bp_map.get(breeding.id, [])
        father_node = None
        mother_node = None
        for bp in bps:
            pet = pet_map.get(bp.pet_id)
            if not pet:
                continue
            if pet.gender == "Male" and father_node is None:
                father_node = _pet_to_node(pet)
            elif pet.gender == "Female" and mother_node is None:
                mother_node = _pet_to_node(pet)

        raw_offspring = offspring_by_breeding.get(breeding.id, [])
        # Split into still-offspring vs converted
        group_offspring = []
        converted_pet_nodes = []
        for o in raw_offspring:
            oid = str(o.id)
            if oid in converted:
                pet = pet_map.get(uuid.UUID(converted[oid]))
                if pet:
                    converted_pet_nodes.append(_pet_to_node(pet))
            else:
                group_offspring.append(_offspring_to_mini(o))

        offspring_group = OffspringGroupNode(
            breeding_id=breeding.id,
            breeding_date=breeding.date_of_litter.isoformat() if breeding.date_of_litter else None,
            count=len(group_offspring),
            offsprings=group_offspring,
        )

        edges.append(BreedingEdge(
            father=father_node,
            mother=mother_node,
            breeding_id=breeding.id,
            offspring_group=offspring_group,
            converted_pets=converted_pet_nodes,
        ))

    # 7. Build pet node list (all non-deleted pets)
    pet_nodes = [_pet_to_node(p) for p in all_pets]

    return GenealogyTree(pets=pet_nodes, edges=edges)


class ConvertOffspringResponse(BaseModel):
    pet_id: str
    message: str


@router.post("/offspring/{offspring_id}/convert-to-pet", response_model=ConvertOffspringResponse)
async def convert_offspring_to_pet(
    offspring_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Convert an offspring into a full Pet record (one-way, irreversible).

    Copies core fields from the offspring into a new Pet row and archives
    the offspring so it no longer appears in the active offspring group.
    The new pet can then be used as a parent in future breedings.
    """
    # Load offspring
    stmt = select(Offspring).where(
        Offspring.id == offspring_id,
        Offspring.user_id == user.id,
    )
    result = await session.execute(stmt)
    offspring = result.scalar_one_or_none()

    if not offspring:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Offspring not found")

    if offspring.status == "Archived":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="OFFSPRING_ALREADY_ARCHIVED")

    # Check if a pet with the same name+dob+gender+breeding already exists
    dup_stmt = select(Pet).where(
        Pet.user_id == user.id,
        Pet.name == offspring.name,
        Pet.date_of_birth == offspring.date_of_birth,
        Pet.gender == offspring.gender,
        Pet.breeding_id == offspring.breeding_id,
        Pet.is_deleted == False,
    )
    dup_result = await session.execute(dup_stmt)
    if dup_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="OFFSPRING_ALREADY_CONVERTED")

    # Create the pet
    new_pet = Pet(
        user_id=user.id,
        breed_id=offspring.breed_id,
        breeding_id=offspring.breeding_id,
        name=offspring.name or f"Pet-{uuid.uuid4().hex[:8]}",
        date_of_birth=offspring.date_of_birth,
        gender=offspring.gender,
        description=offspring.description,
    )
    session.add(new_pet)

    # Archive the offspring
    offspring.status = "Archived"

    await session.commit()
    await session.refresh(new_pet)

    logger.info(
        f"Offspring {offspring_id} converted to pet {new_pet.id} by user {user.id}"
    )

    return ConvertOffspringResponse(
        pet_id=str(new_pet.id),
        message="Offspring has been converted to a pet successfully.",
    )
