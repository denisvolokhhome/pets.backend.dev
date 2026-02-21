#!/usr/bin/env python3
"""
Fix gender values in the database.

This script updates all pets with lowercase gender values ('m', 'f', 'male', 'female')
to use the standardized format ('Male', 'Female').
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.pet import Pet


async def fix_gender_values():
    """Update all pets with non-standard gender values."""
    async with async_session_maker() as session:
        # Get all pets with gender values
        result = await session.execute(
            select(Pet).where(Pet.gender.isnot(None))
        )
        pets = result.scalars().all()
        
        updated_count = 0
        
        for pet in pets:
            old_gender = pet.gender
            new_gender = None
            
            # Normalize gender values
            if old_gender.lower() in ['m', 'male']:
                new_gender = 'Male'
            elif old_gender.lower() in ['f', 'female']:
                new_gender = 'Female'
            
            # Update if changed
            if new_gender and new_gender != old_gender:
                pet.gender = new_gender
                updated_count += 1
                print(f"Updated pet {pet.id} ({pet.name}): '{old_gender}' -> '{new_gender}'")
        
        # Commit all changes
        await session.commit()
        
        print(f"\nTotal pets updated: {updated_count}")
        
        # Verify results
        result = await session.execute(
            select(Pet).where(Pet.gender.isnot(None))
        )
        all_pets = result.scalars().all()
        
        invalid_genders = [
            pet for pet in all_pets 
            if pet.gender not in ['Male', 'Female']
        ]
        
        if invalid_genders:
            print(f"\nWARNING: Found {len(invalid_genders)} pets with invalid gender values:")
            for pet in invalid_genders:
                print(f"  - Pet {pet.id} ({pet.name}): '{pet.gender}'")
        else:
            print("\n✓ All pets now have valid gender values (Male/Female)")


if __name__ == "__main__":
    print("Fixing gender values in database...\n")
    asyncio.run(fix_gender_values())
