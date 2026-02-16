"""Check if breedings table exists."""
import asyncio
from app.database import engine
from sqlalchemy import text


async def check_tables():
    """Check what tables exist in the database."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        tables = [row[0] for row in result]
        print("Tables in database:", tables)
        
        if 'breedings' in tables:
            # Check breedings table structure
            result = await conn.execute(
                text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'breedings'")
            )
            print("\nLitters table columns:")
            for row in result:
                print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")


if __name__ == "__main__":
    asyncio.run(check_tables())
