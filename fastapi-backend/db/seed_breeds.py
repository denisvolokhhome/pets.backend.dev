"""
Seed breeds from breeds.csv into the database.

The CSV must have two columns:
    name  – breed name
    kind  – "dog" or "cat"

Usage:
    python seed_breeds.py
"""
import asyncio
import csv
import sys
from pathlib import Path

# Add parent directory to Python path so we can import app modules
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env from project root before any app imports
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import Settings
from app.models.breed import Breed


async def seed_breeds():
    """Seed breeds from breeds.csv."""
    settings = Settings()

    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    csv_path = ROOT / "db/breeds.csv"
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    print(f"Reading breeds from {csv_path}\n")

    async with async_session_maker() as session:
        added = 0
        skipped = 0

        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            for row_idx, row in enumerate(reader, start=2):
                name = row.get("name", "").strip()
                kind = row.get("kind", "").strip().lower()

                if not name:
                    print(f"Row {row_idx}: Skipping – no breed name")
                    skipped += 1
                    continue

                if kind not in ("dog", "cat"):
                    print(f"Row {row_idx}: Skipping '{name}' – invalid kind '{kind}'")
                    skipped += 1
                    continue

                result = await session.execute(
                    select(Breed).where(Breed.name == name, Breed.kind == kind)
                )
                if result.scalar_one_or_none():
                    print(f"Row {row_idx}: '{name}' ({kind}) already exists, skipping")
                    skipped += 1
                    continue

                session.add(Breed(name=name, kind=kind))
                added += 1
                print(f"Row {row_idx}: Added {kind} '{name}'")

        await session.commit()

        print(f"\n{'='*60}")
        print(f"Seeding complete!")
        print(f"  Added:   {added}")
        print(f"  Skipped: {skipped}")
        print(f"  Total:   {added + skipped}")
        print(f"{'='*60}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_breeds())
