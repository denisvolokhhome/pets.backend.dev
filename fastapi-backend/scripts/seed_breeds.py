"""
Seed breeds from FCI CSV file into the database.

Usage:
    python seed_breeds.py
"""
import asyncio
import csv
import sys
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import Settings
from app.models.breed import Breed
from app.database import Base


async def seed_breeds():
    """Seed breeds from FCI CSV file."""
    # Load settings
    settings = Settings()
    
    # Create async engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,  # Set to True for SQL logging
    )
    
    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Path to CSV file
    csv_path = Path(__file__).parent.parent / "fci-breeds.csv"
    
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)
    
    print(f"Reading breeds from {csv_path}")
    
    # Create session
    async with async_session_maker() as session:
        breeds_added = 0
        breeds_skipped = 0
        
        # Read CSV file
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            print(f"Found columns: {reader.fieldnames}")
            
            for row_idx, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                # Extract breed data from CSV
                breed_name = row.get('name', '').strip()
                breed_group = row.get('group', '').strip()
                
                if not breed_name:
                    print(f"Row {row_idx}: Skipping - no breed name found")
                    breeds_skipped += 1
                    continue
                
                # Check if breed already exists
                result = await session.execute(
                    select(Breed).where(Breed.name == breed_name)
                )
                existing_breed = result.scalar_one_or_none()
                
                if existing_breed:
                    print(f"Row {row_idx}: Breed '{breed_name}' already exists, skipping")
                    breeds_skipped += 1
                    continue
                
                # Create new breed
                breed = Breed(
                    name=breed_name,
                    group=breed_group if breed_group else None
                )
                
                session.add(breed)
                breeds_added += 1
                print(f"Row {row_idx}: Added breed '{breed_name}' (Group: {breed_group or 'N/A'})")
        
        # Commit all changes
        await session.commit()
        
        print(f"\n{'='*60}")
        print(f"Seeding complete!")
        print(f"Breeds added: {breeds_added}")
        print(f"Breeds skipped: {breeds_skipped}")
        print(f"{'='*60}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_breeds())
