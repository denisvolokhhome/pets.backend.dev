"""
Fix the alembic_version table and reapply migrations
"""
import asyncio
from sqlalchemy import text
from app.database import engine

async def fix_migrations():
    async with engine.begin() as conn:
        # Delete the alembic_version entry
        await conn.execute(text("DELETE FROM alembic_version"))
        print("✅ Cleared alembic_version table")
        
    print("\n📝 Now run: alembic upgrade head")

if __name__ == "__main__":
    asyncio.run(fix_migrations())
