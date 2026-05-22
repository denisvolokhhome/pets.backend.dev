"""
Seed script for service categories.

Inserts the 10 initial service categories into the database.
Uses INSERT ... ON CONFLICT DO NOTHING to make the script idempotent —
safe to run multiple times without creating duplicates.

Run with:
    python scripts/seed_service_categories.py
"""
import asyncio
import sys

from sqlalchemy.dialects.postgresql import insert

from app.database import async_session_maker
from app.models.service_category import ServiceCategory


INITIAL_CATEGORIES = [
    {"name": "Grooming",         "slug": "grooming",          "is_active": True},
    {"name": "Dog Walking",      "slug": "dog-walking",       "is_active": True},
    {"name": "Cat Sitting",      "slug": "cat-sitting",       "is_active": True},
    {"name": "Pet Sitting",      "slug": "pet-sitting",       "is_active": True},
    {"name": "Pet Training",     "slug": "pet-training",      "is_active": True},
    {"name": "Pet Boarding",     "slug": "pet-boarding",      "is_active": True},
    {"name": "Veterinary",       "slug": "veterinary",        "is_active": True},
    {"name": "Pet Photography",  "slug": "pet-photography",   "is_active": True},
    {"name": "Pet Transport",    "slug": "pet-transport",     "is_active": True},
    {"name": "Pet Daycare",      "slug": "pet-daycare",       "is_active": True},
]


async def main() -> None:
    """Seed the service_categories table with initial data."""
    print("=" * 60)
    print("Seeding Service Categories")
    print("=" * 60)
    print()

    async with async_session_maker() as session:
        try:
            # Build an INSERT ... ON CONFLICT (slug) DO NOTHING statement
            # so the script is safe to re-run at any time.
            stmt = (
                insert(ServiceCategory)
                .values(INITIAL_CATEGORIES)
                .on_conflict_do_nothing(index_elements=["slug"])
            )
            result = await session.execute(stmt)
            await session.commit()

            inserted = result.rowcount
            skipped = len(INITIAL_CATEGORIES) - inserted

            print(f"✓ Inserted : {inserted} categor{'y' if inserted == 1 else 'ies'}")
            if skipped:
                print(f"⚠ Skipped  : {skipped} (already exist)")
            print()
            print("Done.")

        except Exception as exc:
            await session.rollback()
            print(f"✗ Error: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
