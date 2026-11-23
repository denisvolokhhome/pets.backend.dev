"""
Seed breeds from breeds.csv into the database.

The CSV must have two columns:
    name  – breed name
    kind  – "dog" or "cat"

Safe to run on every deploy: only breeds whose name (case-insensitive) is not
in the database yet are inserted, so rows added to the CSV later reach
databases that were seeded before. Existing breeds are never changed or removed.

Usage:
    python seed_breeds.py
"""
import asyncio
import csv
import sys
from pathlib import Path
from typing import Iterable

# Add parent directory to Python path so we can import app modules
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env from project root before any app imports
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import Settings

# Import Breed model directly to avoid circular import issues
from app.models.breed import Breed

CSV_PATH = ROOT / "db/breeds.csv"


def read_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8", newline="") as csvfile:
        return list(csv.DictReader(csvfile))


def breeds_to_add(rows: Iterable[dict], existing_names: Iterable[str]) -> list[tuple[str, str]]:
    """(name, kind) for valid CSV rows whose name is not already taken."""
    seen = {n.strip().casefold() for n in existing_names}
    new: list[tuple[str, str]] = []
    for row in rows:
        name = (row.get("name") or "").strip()
        kind = (row.get("kind") or "").strip().lower()
        if not name or kind not in ("dog", "cat"):
            print(f"Skipping invalid row: {row}")
            continue
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        new.append((name, kind))
    return new


async def seed_breeds():
    """Insert breeds from breeds.csv that the database does not have yet."""
    if not CSV_PATH.exists():
        print(f"Error: CSV file not found at {CSV_PATH}")
        sys.exit(1)

    engine = create_async_engine(Settings().database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        existing = (await session.execute(select(Breed.name))).scalars().all()
        new = breeds_to_add(read_rows(CSV_PATH), existing)
        for name, kind in new:
            session.add(Breed(name=name, kind=kind))
            print(f"Added {kind} '{name}'")
        await session.commit()

    await engine.dispose()
    print(f"Breed seed complete: {len(new)} added, {len(existing)} already present")


if __name__ == "__main__":
    asyncio.run(seed_breeds())
