"""Pet import service for CSV bulk import of pet records."""
import logging
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.breed import Breed
from app.models.location import Location
from app.models.pet import Pet
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.schemas.pet_import import ImportError as ImportErrorSchema
from app.schemas.pet_import import ImportResult, PetImportRow
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)

# String fields on PetImportRow that should be sanitized.
# Tuple of (field_name, max_length).
_SHORT_STRING_FIELDS = ("name", "breed", "gender", "location", "microchip")
_TEXT_STRING_FIELDS = (
    "description",
    "vaccination",
    "health_certificate",
    "deworming",
    "birth_certificate",
)


class PetImportService:
    """Service for bulk-importing pets from parsed CSV data."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_row(row: PetImportRow) -> PetImportRow:
        """Sanitize all string fields on a single import row."""
        data = row.model_dump()
        for field in _SHORT_STRING_FIELDS:
            val = data.get(field)
            if val is not None:
                data[field] = sanitize_string(val, max_length=255)
        for field in _TEXT_STRING_FIELDS:
            val = data.get(field)
            if val is not None:
                data[field] = sanitize_string(val, max_length=10000)
        return PetImportRow(**data)

    @staticmethod
    def _validate_row(row: PetImportRow) -> list[str]:
        """Return a list of validation error strings for *row* (empty == valid)."""
        errors: list[str] = []
        if not row.name or not row.name.strip():
            errors.append("Name is required")
        if row.gender is not None and row.gender not in ("Male", "Female"):
            errors.append("Gender must be Male or Female")
        if row.weight is not None and row.weight < 0:
            errors.append("Weight must be non-negative")
        return errors


    async def _build_breed_map(
        self, session: AsyncSession
    ) -> dict[str, int]:
        """Return a mapping of lower-cased breed name → breed id."""
        result = await session.execute(select(Breed.id, Breed.name))
        return {name.lower(): bid for bid, name in result.all()}

    async def _build_location_map(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, int]:
        """Return a mapping of lower-cased location name → location id for the breeder."""
        result = await session.execute(
            select(Location.id, Location.name).where(Location.user_id == user_id)
        )
        return {name.lower(): lid for lid, name in result.all()}

    async def _get_current_pet_count(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> int:
        """Return the number of non-deleted pets owned by the user."""
        result = await session.execute(
            select(func.count(Pet.id)).where(
                Pet.user_id == user_id,
                Pet.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def _get_plan_max_pets(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> int:
        """Return the max_pets limit from the user's active plan (or free plan fallback)."""
        sub_result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        subscription = sub_result.scalar_one_or_none()

        if subscription and subscription.status == "active":
            return subscription.plan.max_pets

        # Fall back to the default (free) plan
        free_result = await session.execute(
            select(Plan).where(Plan.is_default == True)  # noqa: E712
        )
        plan = free_result.scalar_one_or_none()
        if plan:
            return plan.max_pets

        # No plan configured — no limit
        return 999_999

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def import_pets(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        pets_data: list[PetImportRow],
    ) -> ImportResult:
        """Validate, resolve references, enforce billing limits, and batch-create pets.

        Args:
            session: Async database session (caller manages the transaction).
            user_id: UUID of the breeder performing the import.
            pets_data: List of parsed CSV rows.

        Returns:
            ImportResult with created/skipped counts, row-level errors, and
            whether the billing plan limit was applied.
        """
        errors: list[ImportErrorSchema] = []

        # Pre-fetch lookup maps
        breed_map = await self._build_breed_map(session)
        location_map = await self._build_location_map(session, user_id)

        # Phase 1: sanitize, validate, and resolve references
        valid_pets: list[dict] = []

        for row in pets_data:
            row = self._sanitize_row(row)

            # Basic field validation
            validation_errors = self._validate_row(row)
            if validation_errors:
                for err in validation_errors:
                    errors.append(ImportErrorSchema(row=row.row_number, reason=err))
                continue

            # Resolve breed
            breed_id = None
            if row.breed:
                breed_id = breed_map.get(row.breed.lower())
                if breed_id is None:
                    errors.append(
                        ImportErrorSchema(
                            row=row.row_number,
                            reason=f"Unknown breed: {row.breed}",
                        )
                    )
                    continue

            # Resolve location
            location_id = None
            if row.location:
                location_id = location_map.get(row.location.lower())
                if location_id is None:
                    errors.append(
                        ImportErrorSchema(
                            row=row.row_number,
                            reason=f"Unknown location: {row.location}",
                        )
                    )
                    continue

            valid_pets.append(
                {
                    "user_id": user_id,
                    "name": row.name.strip(),
                    "breed_id": breed_id,
                    "gender": row.gender,
                    "date_of_birth": row.date_of_birth,
                    "weight": row.weight,
                    "description": row.description,
                    "location_id": location_id,
                    "microchip": row.microchip,
                    "vaccination": row.vaccination,
                    "health_certificate": row.health_certificate,
                    "deworming": row.deworming,
                    "birth_certificate": row.birth_certificate,
                }
            )

        # Phase 2: billing limit enforcement
        current_count = await self._get_current_pet_count(session, user_id)
        max_pets = await self._get_plan_max_pets(session, user_id)

        allowed = min(len(valid_pets), max(0, max_pets - current_count))
        plan_limit_applied = allowed < len(valid_pets)

        pets_to_create = valid_pets[:allowed]
        skipped_by_limit = len(valid_pets) - allowed

        # Phase 3: batch insert within the current transaction
        for pet_data in pets_to_create:
            pet = Pet(**pet_data)
            session.add(pet)

        await session.flush()

        created_count = len(pets_to_create)
        skipped_count = len(errors) + skipped_by_limit

        logger.info(
            "pet_import user_id=%s created=%d skipped=%d plan_limit=%s",
            user_id,
            created_count,
            skipped_count,
            plan_limit_applied,
        )

        return ImportResult(
            created_count=created_count,
            skipped_count=skipped_count,
            errors=errors,
            plan_limit_applied=plan_limit_applied,
        )


# Singleton instance
pet_import_service = PetImportService()
