"""Script to verify the migration was successful."""
import asyncio
from sqlalchemy import text
from app.database import async_session_maker

async def verify_migration():
    """Verify the migration changes."""
    async with async_session_maker() as session:
        print("Checking migration results...\n")
        
        # Check if breedings table exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'breedings'
            )
        """))
        breedings_exists = result.scalar()
        print(f"✓ Breedings table exists: {breedings_exists}")
        
        # Check if litters table still exists (should not)
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'litters'
            )
        """))
        litters_exists = result.scalar()
        print(f"✓ Litters table removed: {not litters_exists}")
        
        # Check if breeding_pets table exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'breeding_pets'
            )
        """))
        breeding_pets_exists = result.scalar()
        print(f"✓ Breeding_pets table exists: {breeding_pets_exists}")
        
        # Check if user_id column exists in breedings
        result = await session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'breedings' AND column_name = 'user_id'
        """))
        user_id_col = result.fetchone()
        if user_id_col:
            print(f"✓ User_id column in breedings: {user_id_col[0]} ({user_id_col[1]}, nullable={user_id_col[2]})")
        
        # Check breeding_id in pets table
        result = await session.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'pets' AND column_name = 'breeding_id'
        """))
        breeding_id_col = result.fetchone()
        if breeding_id_col:
            print(f"✓ Breeding_id column in pets: {breeding_id_col[0]} ({breeding_id_col[1]})")
        
        # Count breedings with user_id
        result = await session.execute(text("SELECT COUNT(*) FROM breedings WHERE user_id IS NOT NULL"))
        breedings_with_user = result.scalar()
        print(f"\n✓ Breedings with user_id: {breedings_with_user}")
        
        # Count total breedings
        result = await session.execute(text("SELECT COUNT(*) FROM breedings"))
        total_breedings = result.scalar()
        print(f"✓ Total breedings: {total_breedings}")
        
        print("\n✅ Migration verification complete!")

if __name__ == "__main__":
    asyncio.run(verify_migration())
