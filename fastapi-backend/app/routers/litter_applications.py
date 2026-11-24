"""
Litter applications: the public litter page, "Apply for this litter", and the breeder's
Applications list with status changes and puppy assignment.

Included before the breedings router so `/api/breedings/public/...` and
`/api/breedings/{id}/applications` are matched here first.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user, require_breeder
from app.models.user import User
from app.schemas.breeding import ApplicationFormRead
from app.schemas.litter_application import (
    ApplicationAssign,
    ApplicationRead,
    ApplicationStatus,
    ApplicationStatusUpdate,
    ApplicationSubmit,
    ApplicationSubmitted,
    LitterApplicationsToggle,
    PublicLitterRead,
)
from app.services.litter_application_service import litter_application_service as svc

router = APIRouter(prefix="/api", tags=["litter-applications"])


# ── public / family ──────────────────────────────────────────────────────────

@router.get("/breedings/public/{breeding_id}", response_model=PublicLitterRead)
async def get_public_litter(breeding_id: int, db: AsyncSession = Depends(get_async_session)):
    """Public litter page: parents, published puppies and whether applications are open."""
    return await svc.public_litter(db, breeding_id)


@router.post("/breedings/public/{breeding_id}/applications", response_model=ApplicationSubmitted,
             status_code=status.HTTP_201_CREATED)
async def submit_application(breeding_id: int, data: ApplicationSubmit,
                             db: AsyncSession = Depends(get_async_session),
                             user: User = Depends(current_active_user)):
    """Submit the litter's application form, for the litter or (with offspring_id) a puppy."""
    return await svc.submit(db, user, breeding_id, data)


# ── breeder ──────────────────────────────────────────────────────────────────

@router.put("/breedings/{breeding_id}/application-form/litter-applications",
            response_model=ApplicationFormRead)
async def set_litter_applications(breeding_id: int, data: LitterApplicationsToggle,
                                  db: AsyncSession = Depends(get_async_session),
                                  breeder: User = Depends(require_breeder)):
    """Open or close "Apply for this litter". Closing keeps past submissions."""
    return await svc.set_accepting(db, breeder, breeding_id, data.accepting_litter_applications)


@router.get("/breedings/{breeding_id}/applications", response_model=list[ApplicationRead])
async def list_applications(breeding_id: int,
                            status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
                            db: AsyncSession = Depends(get_async_session),
                            breeder: User = Depends(require_breeder)):
    return await svc.list_for_breeding(db, breeder, breeding_id, status_filter)


@router.get("/applications/{application_id}", response_model=ApplicationRead)
async def get_application(application_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                          breeder: User = Depends(require_breeder)):
    return await svc.get(db, breeder, application_id)


@router.patch("/applications/{application_id}/status", response_model=ApplicationRead)
async def update_application_status(application_id: uuid.UUID, data: ApplicationStatusUpdate,
                                    db: AsyncSession = Depends(get_async_session),
                                    breeder: User = Depends(require_breeder)):
    return await svc.set_status(db, breeder, application_id, data.status)


@router.post("/applications/{application_id}/assign", response_model=ApplicationRead)
async def assign_puppy(application_id: uuid.UUID, data: ApplicationAssign,
                       db: AsyncSession = Depends(get_async_session),
                       breeder: User = Depends(require_breeder)):
    """Give an available puppy of this litter to the applicant (puppy becomes Reserved)."""
    return await svc.assign(db, breeder, application_id, data.offspring_id)


@router.post("/applications/{application_id}/unassign", response_model=ApplicationRead)
async def unassign_puppy(application_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                         breeder: User = Depends(require_breeder)):
    """Undo an assignment: the puppy is Available again, the application goes back to Waitlisted."""
    return await svc.unassign(db, breeder, application_id)
