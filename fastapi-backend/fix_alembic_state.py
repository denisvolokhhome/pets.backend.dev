"""Fix alembic version state."""
import asyncio
from app.database import engine
from sqlalchemy import text


async def fix_state():
    """Reset alembic version to base."""
    async with engine.begin() as conn:
        # Delete the current version
        await conn.execute(text("DELETE FROM alembic_version"))
        print("Cleared alembic_version table")


if __name__ == "__main__":
    asyncio.run(fix_state())
