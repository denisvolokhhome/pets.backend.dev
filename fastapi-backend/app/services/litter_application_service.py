"""Litter applications: public litter page, submissions, breeder review and puppy assignment."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.breeding import Breeding
from app.models.breeding_application_form import BreedingApplicationForm
from app.models.breeding_pet import BreedingPet
from app.models.litter_application import LitterApplication
from app.models.offspring import Offspring
from app.models.pet import Pet
from app.models.user import User
from app.schemas.breeding import ApplicationFormRead
from app.schemas.litter_application import (
    ApplicationRead,
    ApplicationSubmit,
    ApplicationSubmitted,
    OffspringBrief,
    PublicBreeder,
    PublicLitterRead,
    PublicParent,
    PublicPuppy,
)
from app.schemas.notification import NotificationCreate
from app.services import litter_application_rules as rules
from app.services.notification_preference_service import notification_preference_service
from app.services.notification_service import notification_service
from app.services.offspring_reservation import release_offspring, reserve_offspring

logger = logging.getLogger(__name__)

VOIDED = "Voided"
_ALREADY_APPLIED = "You've already applied. The breeder will be in touch."
_HTTP = {"invalid": status.HTTP_422_UNPROCESSABLE_CONTENT, "conflict": status.HTTP_409_CONFLICT}


def _rule(err: rules.RuleError) -> HTTPException:
    return HTTPException(status_code=_HTTP.get(err.code, 422), detail=str(err))


def _not_found(what: str = "Litter") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _image_url(path: Optional[str]) -> Optional[str]:
    return f"/storage/{path.replace(chr(92), '/')}" if path else None


def _primary_image(images) -> Optional[str]:
    if not images:
        return None
    best = sorted(images, key=lambda i: (not i.is_primary, i.display_order or 0))[0]
    return _image_url(best.image_path)


def _breeder_name(user: User) -> str:
    return user.breedery_name or user.name or "Breeder"


def _is_public(breeding: Breeding) -> bool:
    """A litter is public while it isn't voided/inactive and its breeder account is active."""
    return (breeding.status != VOIDED and bool(breeding.is_active)
            and breeding.user is not None and bool(breeding.user.is_active))


def _brief(o: Optional[Offspring]) -> Optional[OffspringBrief]:
    if o is None:
        return None
    return OffspringBrief(id=o.id, name=o.name, gender=o.gender, status=o.status)


def _read(app: LitterApplication) -> ApplicationRead:
    return ApplicationRead(
        id=app.id, breeding_id=app.breeding_id, source=app.source, status=app.status,
        applicant_id=app.applicant_id, applicant_name=app.applicant_name,
        applicant_email=app.applicant_email, answers=app.answers or [],
        requested_offspring=_brief(app.requested_offspring),
        assigned_offspring=_brief(app.assigned_offspring),
        assigned_at=app.assigned_at, created_at=app.created_at, updated_at=app.updated_at,
    )


class LitterApplicationService:

    # ── loading ──────────────────────────────────────────────────────────

    async def _load_breeding(self, db: AsyncSession, breeding_id: int) -> Optional[Breeding]:
        result = await db.execute(
            select(Breeding).where(Breeding.id == breeding_id).options(
                selectinload(Breeding.user),
                selectinload(Breeding.application_form),
            ).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _load_owned_breeding(self, db: AsyncSession, breeder: User, breeding_id: int) -> Breeding:
        breeding = await self._load_breeding(db, breeding_id)
        if breeding is None or breeding.user_id != breeder.id:
            raise _not_found()
        return breeding

    async def _fetch(self, db: AsyncSession, app_id: uuid.UUID, *, lock: bool = False) -> Optional[LitterApplication]:
        stmt = select(LitterApplication).where(LitterApplication.id == app_id).options(
            selectinload(LitterApplication.requested_offspring),
            selectinload(LitterApplication.assigned_offspring),
        ).execution_options(populate_existing=True)
        if lock:
            stmt = stmt.with_for_update(of=LitterApplication)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _load_owned(self, db: AsyncSession, breeder: User, app_id: uuid.UUID, *,
                          lock: bool = False) -> LitterApplication:
        app = await self._fetch(db, app_id, lock=lock)
        # Only the litter owner may see or change an application
        if app is None or app.breeder_id != breeder.id:
            raise _not_found("Application")
        return app

    async def _commit(self, db: AsyncSession, conflict_detail: str) -> None:
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_detail)

    # ── public ───────────────────────────────────────────────────────────

    async def public_litter(self, db: AsyncSession, breeding_id: int) -> PublicLitterRead:
        breeding = await self._load_breeding(db, breeding_id)
        if breeding is None or not _is_public(breeding):
            raise _not_found()

        parents_q = await db.execute(
            select(Pet).join(BreedingPet, BreedingPet.pet_id == Pet.id)
            .where(BreedingPet.breeding_id == breeding_id, Pet.is_deleted.is_(False))
            .options(selectinload(Pet.breed), selectinload(Pet.images))
        )
        parents = [
            PublicParent(id=p.id, name=p.name, gender=p.gender,
                         breed_name=p.breed.name if p.breed else None,
                         image_url=_primary_image(p.images) or _image_url(p.image_path))
            for p in parents_q.scalars().unique().all()
        ]

        puppies_q = await db.execute(
            select(Offspring).where(
                Offspring.breeding_id == breeding_id,
                Offspring.is_published.is_(True),
                Offspring.status != "Archived",
            ).options(selectinload(Offspring.images)).order_by(Offspring.created_at)
        )
        puppies = [
            PublicPuppy(id=o.id, name=o.name, gender=o.gender, status=o.status,
                        price=float(o.price) if o.price is not None else None,
                        image_url=_primary_image(o.images))
            for o in puppies_q.scalars().all()
        ]

        form = breeding.application_form
        fields = form.form_fields if form and form.form_fields else None
        return PublicLitterRead(
            id=breeding.id, description=breeding.description, stage=breeding.stage,
            date_of_litter=breeding.date_of_litter,
            breeder=PublicBreeder(id=breeding.user.id, name=_breeder_name(breeding.user)),
            parents=parents, puppies=puppies, application_form=fields,
            accepting_applications=bool(fields and form.accepting_litter_applications),
        )

    async def submit(self, db: AsyncSession, applicant: User, breeding_id: int,
                     data: ApplicationSubmit) -> ApplicationSubmitted:
        breeding = await self._load_breeding(db, breeding_id)
        if breeding is None:
            raise _not_found()
        if not _is_public(breeding):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="This litter is no longer accepting applications")
        if breeding.user_id == applicant.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="You can't apply to your own litter")
        form: Optional[BreedingApplicationForm] = breeding.application_form
        if form is None or not form.form_fields:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="This litter has no application form")

        if data.offspring_id is not None:
            # Existing puppy-page flow: needs only the form and a public puppy of this litter
            offspring = await db.get(Offspring, data.offspring_id)
            if (offspring is None or offspring.breeding_id != breeding.id
                    or not offspring.is_published or offspring.status == "Archived"):
                raise _not_found("Offspring")
            source = "offspring"
        else:
            if not form.accepting_litter_applications:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Applications for this litter are closed")
            source = "litter"

        try:
            answers = rules.snapshot_answers(form.form_fields, data.answers)
        except rules.RuleError as e:
            raise _rule(e)

        # One open application per family per litter (per puppy for the puppy flow);
        # a declined family may apply again.
        dup = select(LitterApplication.id).where(
            LitterApplication.breeding_id == breeding.id,
            LitterApplication.applicant_id == applicant.id,
            LitterApplication.source == source,
            LitterApplication.status != "declined",
        )
        if data.offspring_id is not None:
            dup = dup.where(LitterApplication.requested_offspring_id == data.offspring_id)
        if (await db.execute(dup.limit(1))).first() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ALREADY_APPLIED)

        app = LitterApplication(
            breeding_id=breeding.id, breeder_id=breeding.user_id, applicant_id=applicant.id,
            applicant_name=(applicant.name or applicant.email)[:255],
            applicant_email=(applicant.email or "")[:255] or None,
            source=source, requested_offspring_id=data.offspring_id,
            answers=answers, status="new",
        )
        db.add(app)
        # The partial unique index backs up the check above under a double submit
        await self._commit(db, _ALREADY_APPLIED)
        await db.refresh(app)
        await self._notify_breeder(db, breeding, applicant, app.id)
        return ApplicationSubmitted(id=app.id, breeding_id=app.breeding_id, status=app.status,
                                    created_at=app.created_at)

    async def _notify_breeder(self, db: AsyncSession, breeding: Breeding, applicant: User,
                              application_id: uuid.UUID) -> None:
        try:
            if not await notification_preference_service.should_send_notification(
                    db, breeding.user_id, "litter_application"):
                return
            await notification_service.create_notification(db, NotificationCreate(
                user_id=breeding.user_id, type="litter_application",
                title="New litter application"[:255],
                message=f"{applicant.name or 'A family'} applied for your litter"
                        f"{(' — ' + breeding.description) if breeding.description else ''}."[:1000],
                related_id=application_id, related_type="litter_application",
            ))
        except Exception:  # a failed notification must never fail the (already saved) application
            logger.exception("Failed to notify breeder %s about an application", breeding.user_id)
            await db.rollback()

    async def _notify_applicant(self, db: AsyncSession, app: LitterApplication, *, title: str,
                                message: str) -> None:
        """In-app notification + email to the family. Best effort: the change is already saved."""
        if app.applicant_id is None:
            return
        try:
            if not await notification_preference_service.should_send_notification(
                    db, app.applicant_id, "application_update"):
                return
            await notification_service.create_notification(db, NotificationCreate(
                user_id=app.applicant_id, type="application_update", title=title[:255],
                message=message[:1000], related_id=app.id, related_type="litter_application_family",
            ))
        except Exception:
            logger.exception("Failed to notify applicant %s about application %s", app.applicant_id, app.id)
            await db.rollback()

    # ── breeder ──────────────────────────────────────────────────────────

    async def set_accepting(self, db: AsyncSession, breeder: User, breeding_id: int,
                            accepting: bool) -> ApplicationFormRead:
        breeding = await self._load_owned_breeding(db, breeder, breeding_id)
        form = breeding.application_form
        if form is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Add an application form first")
        if accepting and breeding.status == VOIDED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="A voided litter can't accept applications")
        form.accepting_litter_applications = accepting
        await db.commit()
        await db.refresh(form)
        return ApplicationFormRead.model_validate(form, from_attributes=True)

    async def list_for_breeding(self, db: AsyncSession, breeder: User, breeding_id: int,
                                status_filter: Optional[str]) -> list[ApplicationRead]:
        await self._load_owned_breeding(db, breeder, breeding_id)
        stmt = select(LitterApplication).where(
            LitterApplication.breeding_id == breeding_id,
            LitterApplication.breeder_id == breeder.id,
        ).options(
            selectinload(LitterApplication.requested_offspring),
            selectinload(LitterApplication.assigned_offspring),
        ).order_by(LitterApplication.created_at.desc())
        if status_filter:
            stmt = stmt.where(LitterApplication.status == status_filter)
        result = await db.execute(stmt)
        return [_read(a) for a in result.scalars().all()]

    async def get(self, db: AsyncSession, breeder: User, app_id: uuid.UUID) -> ApplicationRead:
        return _read(await self._load_owned(db, breeder, app_id))

    async def set_status(self, db: AsyncSession, breeder: User, app_id: uuid.UUID,
                         new_status: str) -> ApplicationRead:
        app = await self._load_owned(db, breeder, app_id, lock=True)
        try:
            rules.check_manual_status_change(app.status, new_status)
        except rules.RuleError as e:
            raise _rule(e)
        previous = app.status
        app.status = new_status
        await db.commit()
        app = await self._fetch(db, app.id)
        if new_status == "waitlisted" and previous != "waitlisted":
            # The breeder accepted the application onto this litter's waitlist
            await self._notify_applicant(
                db, app, title=f"You're on the waitlist — {_breeder_name(breeder)}",
                message=f"{_breeder_name(breeder)} accepted your application and added you to the waitlist "
                        f"for their litter. They'll be in touch when puppies are ready.")
        return _read(app)

    async def assign(self, db: AsyncSession, breeder: User, app_id: uuid.UUID,
                     offspring_id: uuid.UUID) -> ApplicationRead:
        # Lock the application first so one application can't take two puppies at once
        app = await self._load_owned(db, breeder, app_id, lock=True)
        try:
            rules.check_can_assign(app.status)
        except rules.RuleError as e:
            raise _rule(e)
        reserved = await reserve_offspring(db, offspring_id=offspring_id,
                                           breeding_id=app.breeding_id, breeder_id=breeder.id)
        if not reserved:  # nothing was written; the request's session rolls back on the error
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="That puppy isn't available any more. Pick another available puppy from this litter.")
        app.assigned_offspring_id = offspring_id
        app.status = "assigned"
        app.assigned_at = datetime.now(timezone.utc)
        await self._commit(db, "That puppy is already assigned to another family")
        app = await self._fetch(db, app.id)
        puppy = (app.assigned_offspring.name if app.assigned_offspring and app.assigned_offspring.name
                 else "a puppy")
        await self._notify_applicant(
            db, app, title=f"A puppy is reserved for you — {_breeder_name(breeder)}",
            message=f"{_breeder_name(breeder)} reserved {puppy} for you from their litter.")
        return _read(app)

    async def unassign(self, db: AsyncSession, breeder: User, app_id: uuid.UUID) -> ApplicationRead:
        app = await self._load_owned(db, breeder, app_id, lock=True)
        try:
            rules.check_can_unassign(app.status)
        except rules.RuleError as e:
            raise _rule(e)
        if app.assigned_offspring_id is not None:
            await release_offspring(db, offspring_id=app.assigned_offspring_id, breeder_id=breeder.id,
                                    releasing_application=app.id)
        app.assigned_offspring_id = None
        app.assigned_at = None
        app.status = rules.UNASSIGNED_STATUS
        await db.commit()
        return _read(await self._fetch(db, app.id))


litter_application_service = LitterApplicationService()
