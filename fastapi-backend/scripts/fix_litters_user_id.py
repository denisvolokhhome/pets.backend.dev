"""Script to check and fix litters without user_id before migration."""
import asyncio
from sqlalchemy import select, text
from app.database import async_session_maker

async def check_and_fix_litters():
    """Check for litters without parent pets and handle them."""
    async with async_session_maker() as session:
        # Check how many litters exist
        result = await session.execute(text("SELECT COUNT(*) FROM litters"))
        total_litters = result.scalar()
        print(f"Total litters: {total_litters}")
        
        # Check how many litters have parent pets
        result = await session.execute(text("""
            SELECT COUNT(DISTINCT litter_id) 
            FROM litter_pets
        """))
        litters_with_parents = result.scalar()
        print(f"Litters with parent pets: {litters_with_parents}")
        
        # Check litters without parent pets
        result = await session.execute(text("""
            SELECT id FROM litters 
            WHERE id NOT IN (SELECT DISTINCT litter_id FROM litter_pets)
        """))
        orphan_litters = result.fetchall()
        print(f"Litters without parent pets: {len(orphan_litters)}")
        
        if orphan_litters:
            print("\nOrphan litter IDs:", [row[0] for row in orphan_litters])
            
            # Option 1: Delete orphan litters (they have no parent pets anyway)
            print("\nDeleting orphan litters...")
            await session.execute(text("""
                DELETE FROM litters 
                WHERE id NOT IN (SELECT DISTINCT litter_id FROM litter_pets)
            """))
            await session.commit()
            print("Orphan litters deleted.")
        else:
            print("\nAll litters have parent pets. Ready for migration!")

if __name__ == "__main__":
    asyncio.run(check_and_fix_litters())
