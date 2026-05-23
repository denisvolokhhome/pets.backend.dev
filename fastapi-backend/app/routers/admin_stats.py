"""Admin statistics API endpoints for the dashboard."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, func, case, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.models.user import User
from app.models.pet import Pet
from app.models.breeding import Breeding
from app.models.offspring import Offspring
from app.models.offspring_favorite import OffspringFavorite
from app.models.message import Message
from app.models.notification import Notification
from app.models.location import Location
from app.models.user_contact import UserContact

router = APIRouter(prefix="/api/admin/stats", tags=["admin-stats"])
settings = Settings()


async def verify_admin_key(x_admin_key: str = Header(...)):
    """Verify the admin API key from request header."""
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return True


@router.get("/overview")
async def get_overview(
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get high-level overview statistics."""
    # Total users by type
    user_counts = await session.execute(
        select(
            func.count().label("total"),
            func.count().filter(User.is_breeder == True).label("breeders"),
            func.count().filter(User.is_breeder == False).label("pet_seekers"),
            func.count().filter(User.is_active == True).label("active"),
            func.count().filter(User.is_verified == True).label("verified"),
        ).select_from(User)
    )
    uc = user_counts.one()

    # Breeders with completed profiles (have name, location, contact, at least 1 pet)
    completed_breeders = await session.execute(
        select(func.count(func.distinct(User.id))).select_from(User).join(
            Location, and_(Location.user_id == User.id, Location.location_type == "user")
        ).join(
            UserContact, UserContact.user_id == User.id
        ).where(
            and_(
                User.is_breeder == True,
                User.breedery_name.isnot(None),
                User.breedery_name != "",
            )
        )
    )
    completed_count = completed_breeders.scalar() or 0

    # Content counts
    pet_count = await session.execute(
        select(func.count()).select_from(Pet).where(Pet.is_deleted == False)
    )
    breeding_count = await session.execute(
        select(func.count()).select_from(Breeding)
    )
    offspring_count = await session.execute(
        select(func.count()).select_from(Offspring)
    )
    message_count = await session.execute(
        select(func.count()).select_from(Message)
    )
    favorite_count = await session.execute(
        select(func.count()).select_from(OffspringFavorite)
    )

    return {
        "users": {
            "total": uc.total,
            "breeders": uc.breeders,
            "pet_seekers": uc.pet_seekers,
            "active": uc.active,
            "verified": uc.verified,
            "breeders_completed_profile": completed_count,
        },
        "content": {
            "pets": pet_count.scalar() or 0,
            "breedings": breeding_count.scalar() or 0,
            "offsprings": offspring_count.scalar() or 0,
            "messages": message_count.scalar() or 0,
            "favorites": favorite_count.scalar() or 0,
        },
    }


@router.get("/registrations-over-time")
async def get_registrations_over_time(
    days: int = 90,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get user registration counts grouped by day."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(
            func.date_trunc("day", User.created_at).label("day"),
            User.is_breeder,
            func.count().label("count"),
        )
        .where(User.created_at >= since)
        .group_by("day", User.is_breeder)
        .order_by("day")
    )
    rows = result.all()
    return [
        {
            "date": r.day.isoformat() if r.day else None,
            "is_breeder": r.is_breeder,
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/offspring-status")
async def get_offspring_status_breakdown(
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get offspring counts by status."""
    result = await session.execute(
        select(Offspring.status, func.count().label("count"))
        .group_by(Offspring.status)
    )
    return [{"status": r.status, "count": r.count} for r in result.all()]


@router.get("/activity-over-time")
async def get_activity_over_time(
    days: int = 30,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get daily activity counts (messages, favorites, notifications)."""
    since = datetime.utcnow() - timedelta(days=days)

    messages = await session.execute(
        select(
            func.date_trunc("day", Message.created_at).label("day"),
            func.count().label("count"),
        )
        .where(Message.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    favorites = await session.execute(
        select(
            func.date_trunc("day", OffspringFavorite.created_at).label("day"),
            func.count().label("count"),
        )
        .where(OffspringFavorite.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    notifications = await session.execute(
        select(
            func.date_trunc("day", Notification.created_at).label("day"),
            func.count().label("count"),
        )
        .where(Notification.created_at >= since)
        .group_by("day")
        .order_by("day")
    )

    return {
        "messages": [{"date": r.day.isoformat(), "count": r.count} for r in messages.all()],
        "favorites": [{"date": r.day.isoformat(), "count": r.count} for r in favorites.all()],
        "notifications": [{"date": r.day.isoformat(), "count": r.count} for r in notifications.all()],
    }


@router.get("/top-breeders")
async def get_top_breeders(
    limit: int = 10,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get top breeders by offspring count."""
    result = await session.execute(
        select(
            User.id,
            User.name,
            User.email,
            User.breedery_name,
            func.count(Offspring.id).label("offspring_count"),
        )
        .join(Offspring, Offspring.user_id == User.id)
        .where(User.is_breeder == True)
        .group_by(User.id, User.name, User.email, User.breedery_name)
        .order_by(func.count(Offspring.id).desc())
        .limit(limit)
    )
    return [
        {
            "id": str(r.id),
            "name": r.name or r.email,
            "breedery_name": r.breedery_name,
            "offspring_count": r.offspring_count,
        }
        for r in result.all()
    ]


@router.get("/breeds-popularity")
async def get_breeds_popularity(
    limit: int = 15,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get most popular breeds by offspring count."""
    from app.models.breed import Breed

    result = await session.execute(
        select(
            Breed.name,
            func.count(Offspring.id).label("count"),
        )
        .join(Offspring, Offspring.breed_id == Breed.id)
        .group_by(Breed.name)
        .order_by(func.count(Offspring.id).desc())
        .limit(limit)
    )
    return [{"breed": r.name, "count": r.count} for r in result.all()]


@router.get("/locations-summary")
async def get_locations_summary(
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get breeder distribution by state/country."""
    result = await session.execute(
        select(
            Location.state,
            Location.country,
            func.count().label("count"),
        )
        .where(Location.location_type == "user")
        .group_by(Location.state, Location.country)
        .order_by(func.count().desc())
    )
    return [
        {"state": r.state, "country": r.country, "count": r.count}
        for r in result.all()
    ]


@router.get("/recent-users")
async def get_recent_users(
    limit: int = 20,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get most recently registered users."""
    result = await session.execute(
        select(
            User.id, User.email, User.name, User.is_breeder,
            User.is_active, User.is_verified, User.breedery_name,
            User.created_at,
        )
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(r.id),
            "email": r.email,
            "name": r.name,
            "is_breeder": r.is_breeder,
            "is_active": r.is_active,
            "is_verified": r.is_verified,
            "breedery_name": r.breedery_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.all()
    ]



@router.get("/breeder-details")
async def get_breeder_details(
    limit: int = 50,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get detailed breeder list with profile completion info."""
    from sqlalchemy.orm import aliased

    result = await session.execute(
        select(
            User.id, User.email, User.name, User.breedery_name,
            User.is_active, User.is_verified, User.profile_image_path,
            User.created_at,
            func.count(func.distinct(Pet.id)).filter(Pet.is_deleted == False).label("pet_count"),
            func.count(func.distinct(Breeding.id)).label("breeding_count"),
            func.count(func.distinct(Offspring.id)).label("offspring_count"),
        )
        .outerjoin(Pet, and_(Pet.user_id == User.id, Pet.is_deleted == False))
        .outerjoin(Breeding, Breeding.user_id == User.id)
        .outerjoin(Offspring, Offspring.user_id == User.id)
        .where(User.is_breeder == True)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    rows = result.all()

    # Check profile completion per breeder
    loc_result = await session.execute(
        select(Location.user_id, func.count().label("c"))
        .where(Location.location_type == "user")
        .group_by(Location.user_id)
    )
    has_location = {r.user_id for r in loc_result.all()}

    contact_result = await session.execute(
        select(func.distinct(UserContact.user_id))
    )
    has_contact = {r[0] for r in contact_result.all()}

    return [
        {
            "id": str(r.id),
            "email": r.email,
            "name": r.name,
            "breedery_name": r.breedery_name,
            "is_active": r.is_active,
            "is_verified": r.is_verified,
            "has_profile_image": bool(r.profile_image_path),
            "has_location": r.id in has_location,
            "has_contact": r.id in has_contact,
            "has_breedery_name": bool(r.breedery_name),
            "pet_count": r.pet_count,
            "breeding_count": r.breeding_count,
            "offspring_count": r.offspring_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/breeder-profile-completion")
async def get_breeder_profile_completion(
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get breeder profile completion breakdown."""
    total = await session.execute(
        select(func.count()).select_from(User).where(User.is_breeder == True)
    )
    total_count = total.scalar() or 0

    has_name = await session.execute(
        select(func.count()).select_from(User).where(
            and_(User.is_breeder == True, User.breedery_name.isnot(None), User.breedery_name != "")
        )
    )
    has_image = await session.execute(
        select(func.count()).select_from(User).where(
            and_(User.is_breeder == True, User.profile_image_path.isnot(None))
        )
    )
    has_loc = await session.execute(
        select(func.count(func.distinct(User.id))).select_from(User).join(
            Location, and_(Location.user_id == User.id, Location.location_type == "user")
        ).where(User.is_breeder == True)
    )
    has_contact = await session.execute(
        select(func.count(func.distinct(User.id))).select_from(User).join(
            UserContact, UserContact.user_id == User.id
        ).where(User.is_breeder == True)
    )
    has_pets = await session.execute(
        select(func.count(func.distinct(User.id))).select_from(User).join(
            Pet, and_(Pet.user_id == User.id, Pet.is_deleted == False)
        ).where(User.is_breeder == True)
    )
    has_breeding = await session.execute(
        select(func.count(func.distinct(User.id))).select_from(User).join(
            Breeding, Breeding.user_id == User.id
        ).where(User.is_breeder == True)
    )

    return {
        "total_breeders": total_count,
        "steps": {
            "breedery_name": has_name.scalar() or 0,
            "profile_image": has_image.scalar() or 0,
            "location": has_loc.scalar() or 0,
            "contact_info": has_contact.scalar() or 0,
            "pets_added": has_pets.scalar() or 0,
            "breeding_created": has_breeding.scalar() or 0,
        },
    }


@router.get("/pet-seeker-details")
async def get_pet_seeker_details(
    limit: int = 50,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get detailed pet seeker list with engagement info."""
    result = await session.execute(
        select(
            User.id, User.email, User.name,
            User.is_active, User.is_verified,
            User.created_at,
            func.count(func.distinct(OffspringFavorite.id)).label("favorite_count"),
            func.count(func.distinct(Message.id)).label("message_count"),
        )
        .outerjoin(OffspringFavorite, OffspringFavorite.user_id == User.id)
        .outerjoin(Message, Message.sender_id == User.id)
        .where(User.is_breeder == False)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(r.id),
            "email": r.email,
            "name": r.name,
            "is_active": r.is_active,
            "is_verified": r.is_verified,
            "favorite_count": r.favorite_count,
            "message_count": r.message_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.all()
    ]


@router.get("/pet-seeker-engagement")
async def get_pet_seeker_engagement(
    days: int = 30,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get pet seeker engagement metrics over time."""
    since = datetime.utcnow() - timedelta(days=days)

    # Favorites over time by pet seekers
    fav_over_time = await session.execute(
        select(
            func.date_trunc("day", OffspringFavorite.created_at).label("day"),
            func.count().label("count"),
        )
        .join(User, User.id == OffspringFavorite.user_id)
        .where(and_(User.is_breeder == False, OffspringFavorite.created_at >= since))
        .group_by("day")
        .order_by("day")
    )

    # Messages sent by pet seekers over time
    msg_over_time = await session.execute(
        select(
            func.date_trunc("day", Message.created_at).label("day"),
            func.count().label("count"),
        )
        .join(User, User.id == Message.sender_id)
        .where(and_(User.is_breeder == False, Message.created_at >= since))
        .group_by("day")
        .order_by("day")
    )

    # Top favorited offsprings
    from app.models.breed import Breed
    top_favorited = await session.execute(
        select(
            Offspring.id, Offspring.name,
            Breed.name.label("breed_name"),
            func.count(OffspringFavorite.id).label("fav_count"),
        )
        .join(OffspringFavorite, OffspringFavorite.offspring_id == Offspring.id)
        .outerjoin(Breed, Breed.id == Offspring.breed_id)
        .group_by(Offspring.id, Offspring.name, Breed.name)
        .order_by(func.count(OffspringFavorite.id).desc())
        .limit(10)
    )

    return {
        "favorites_over_time": [{"date": r.day.isoformat(), "count": r.count} for r in fav_over_time.all()],
        "messages_over_time": [{"date": r.day.isoformat(), "count": r.count} for r in msg_over_time.all()],
        "top_favorited": [
            {"id": str(r.id), "name": r.name, "breed": r.breed_name, "favorites": r.fav_count}
            for r in top_favorited.all()
        ],
    }



@router.get("/breeds")
async def get_all_breeds(
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all breeds with colour counts and usage stats."""
    from app.models.breed import Breed, BreedColour

    result = await session.execute(
        select(
            Breed.id, Breed.name, Breed.kind, Breed.created_at, Breed.updated_at,
            func.count(func.distinct(Offspring.id)).label("offspring_count"),
            func.count(func.distinct(Pet.id)).label("pet_count"),
        )
        .outerjoin(Offspring, Offspring.breed_id == Breed.id)
        .outerjoin(Pet, Pet.breed_id == Breed.id)
        .group_by(Breed.id)
        .order_by(Breed.kind, Breed.name)
    )
    breeds = result.all()

    # Get colours per breed
    colours_result = await session.execute(
        select(BreedColour.breed_id, BreedColour.id, BreedColour.name)
        .order_by(BreedColour.breed_id, BreedColour.name)
    )
    colours_by_breed: dict = {}
    for c in colours_result.all():
        colours_by_breed.setdefault(c.breed_id, []).append({"id": c.id, "name": c.name})

    return [
        {
            "id": b.id,
            "name": b.name,
            "kind": b.kind,
            "offspring_count": b.offspring_count,
            "pet_count": b.pet_count,
            "colours": colours_by_breed.get(b.id, []),
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        }
        for b in breeds
    ]


@router.post("/breeds")
async def create_breed(
    breed: dict,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a single breed via admin."""
    from app.models.breed import Breed

    name = breed.get("name", "").strip()
    kind = breed.get("kind", "dog").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Breed name is required")
    if kind not in ("dog", "cat"):
        raise HTTPException(status_code=400, detail="Kind must be dog or cat")

    existing = await session.execute(select(Breed).where(Breed.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Breed '{name}' already exists")

    new_breed = Breed(name=name, kind=kind)
    session.add(new_breed)
    await session.commit()
    await session.refresh(new_breed)
    return {"id": new_breed.id, "name": new_breed.name, "kind": new_breed.kind}


@router.put("/breeds/{breed_id}")
async def update_breed(
    breed_id: int,
    breed: dict,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a breed via admin."""
    from app.models.breed import Breed

    result = await session.execute(select(Breed).where(Breed.id == breed_id))
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Breed not found")

    if "name" in breed and breed["name"].strip():
        # Check uniqueness
        dup = await session.execute(
            select(Breed).where(Breed.name == breed["name"].strip(), Breed.id != breed_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Breed '{breed['name']}' already exists")
        existing.name = breed["name"].strip()
    if "kind" in breed:
        if breed["kind"] not in ("dog", "cat"):
            raise HTTPException(status_code=400, detail="Kind must be dog or cat")
        existing.kind = breed["kind"]

    await session.commit()
    await session.refresh(existing)
    return {"id": existing.id, "name": existing.name, "kind": existing.kind}


@router.delete("/breeds/{breed_id}")
async def delete_breed(
    breed_id: int,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a breed via admin."""
    from app.models.breed import Breed

    result = await session.execute(select(Breed).where(Breed.id == breed_id))
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Breed not found")

    try:
        await session.delete(existing)
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete breed — it is in use by pets or offsprings")
    return {"ok": True}


@router.post("/breeds/bulk-import")
async def bulk_import_breeds(
    breeds: list[dict],
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Bulk import breeds. Skips duplicates. Expects list of {name, kind}."""
    from app.models.breed import Breed

    existing_result = await session.execute(select(Breed.name))
    existing_names = {r.name.lower() for r in existing_result.all()}

    created = 0
    skipped = 0
    errors = []
    for i, b in enumerate(breeds):
        name = str(b.get("name", "")).strip()
        kind = str(b.get("kind", "dog")).strip().lower()
        if not name:
            errors.append(f"Row {i+1}: empty name")
            continue
        if kind not in ("dog", "cat"):
            errors.append(f"Row {i+1}: invalid kind '{kind}'")
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        session.add(Breed(name=name, kind=kind))
        existing_names.add(name.lower())
        created += 1

    await session.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
