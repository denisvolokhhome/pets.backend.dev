"""
Public, read-only breeds API: list, autocomplete, get by id.

Breeds are seeded (db/seed_breeds.py) and managed from the admin dashboard through
/api/admin/stats/breeds (X-Admin-Key). There are deliberately no public write routes.
"""
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.breed import Breed
from app.schemas.breed import BreedRead


router = APIRouter(
    prefix="/api/breeds",
    tags=["breeds"],
    responses={
        404: {"description": "Breed not found"},
        400: {"description": "Breed with this name already exists"},
    }
)

# The breed list is near-static and requested on most pages, so it is cached in-process.
# Admin breed writes clear it; with several workers (or seed scripts writing to the DB)
# other processes may serve a stale list for at most LIST_CACHE_TTL_SECONDS.
# Only first pages (skip=0) are cached, and at most LIST_CACHE_MAX_ENTRIES of them, so odd
# query strings can't grow the cache without bound.
LIST_CACHE_TTL_SECONDS = 300
LIST_CACHE_MAX_ENTRIES = 16
_list_cache: dict[tuple, tuple[float, List[BreedRead]]] = {}


def clear_breed_list_cache() -> None:
    _list_cache.clear()


@router.get("", response_model=List[BreedRead], include_in_schema=False)  # no 307 hop
@router.get("/", response_model=List[BreedRead])
async def list_breeds(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    kind: Optional[str] = Query(
        None,
        description="Filter breeds by pet type: 'dog' or 'cat'",
        pattern="^(dog|cat)$",
    ),
) -> List[BreedRead]:
    """
    List all breeds, optionally filtered by pet type (kind).

    This endpoint is public and does not require authentication.
    Results are ordered alphabetically by name.

    **Query parameters:**
    - skip: Number of records to skip (default: 0)
    - limit: Maximum number of records to return (default: 100)
    - kind: Optional filter — 'dog', 'cat', 'cow', or 'horse'
    """
    response.headers["Cache-Control"] = f"public, max-age={LIST_CACHE_TTL_SECONDS}"
    key = (limit, kind)
    now = time.monotonic()
    cached = _list_cache.get(key) if skip == 0 else None
    if cached and now - cached[0] < LIST_CACHE_TTL_SECONDS:
        return cached[1]

    query = select(Breed)

    if kind:
        query = query.where(Breed.kind == kind)

    query = query.offset(skip).limit(limit).order_by(Breed.name)

    result = await session.execute(query)
    breeds = [BreedRead.model_validate(b, from_attributes=True) for b in result.scalars().all()]
    if skip == 0:
        for stale in [k for k, (at, _) in _list_cache.items() if now - at >= LIST_CACHE_TTL_SECONDS]:
            del _list_cache[stale]
        if key in _list_cache or len(_list_cache) < LIST_CACHE_MAX_ENTRIES:
            _list_cache[key] = (now, breeds)
    return breeds


@router.get("/autocomplete", response_model=List[BreedRead])
async def autocomplete_breeds(
    search_term: str = Query(..., min_length=2, max_length=100, description="Search term for breed name (minimum 2 characters)"),
    kind: Optional[str] = Query(None, pattern="^(dog|cat)$", description="Filter by animal kind"),
    session: AsyncSession = Depends(get_async_session),
) -> List[Breed]:
    """
    Search breeds by partial name match for autocomplete functionality.
    
    This endpoint is public and does not require authentication.
    Returns up to 10 breeds that match the search term, ordered by relevance
    (exact matches first, then partial matches).
    
    **Query parameters:**
    - search_term: Partial breed name to search for (minimum 2 characters)
    
    **Matching logic:**
    - Case-insensitive partial matching
    - Matches breed name or code
    - Results ordered by relevance (exact matches first)
    - Limited to 10 results
    
    **Example request:**
    ```
    GET /api/breeds/autocomplete?search_term=lab
    ```
    
    **Example response:**
    ```json
    [
        {
            "id": 1,
            "name": "Labrador Retriever",
            "code": "122",
            "group": "Sporting",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": 2,
            "name": "Black Labrador",
            "code": "122B",
            "group": "Sporting",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    ]
    ```
    
    **Requirements Validated:**
    - 13.5: GET endpoint with search_term parameter validation
    - 13.6: Returns JSON array of breed objects matching search term
    - 13.7: Includes breed_id, breed_name, and breed_code in response
    """
    # Create case-insensitive search pattern
    search_pattern = f"%{search_term}%"
    
    # Query breeds matching the search term in name
    # Order by exact match first, then partial matches
    query = (
        select(Breed)
        .where(
            func.lower(Breed.name).like(func.lower(search_pattern))
        )
    )

    if kind:
        query = query.where(Breed.kind == kind)

    query = (
        query
        .order_by(
            # Exact matches first
            func.lower(Breed.name) == func.lower(search_term),
            # Then alphabetically
            Breed.name
        )
        .limit(10)
    )
    
    result = await session.execute(query)
    breeds = result.scalars().all()
    
    return list(breeds)


@router.get("/{breed_id}", response_model=BreedRead)
async def get_breed(
    breed_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> Breed:
    """
    Get a single breed by ID.
    
    This endpoint is public and does not require authentication.
    """
    query = select(Breed).where(Breed.id == breed_id)
    result = await session.execute(query)
    breed = result.scalar_one_or_none()
    
    if breed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breed not found"
        )
    
    return breed
