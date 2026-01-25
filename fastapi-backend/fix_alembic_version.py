#!/usr/bin/env python3
"""Fix alembic version table."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import get_async_session


async def fix_version():
    """Reset alembic version to base."""
    print("Resetting alembic version...")
    
    try:
        async for session in get_async_session():
            # Delete the version record
            await session.execute(text("DELETE FROM alembic_version"))
            await session.commit()
            print("✓ Alembic version reset")
            break
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(fix_version())
    sys.exit(0 if result else 1)
