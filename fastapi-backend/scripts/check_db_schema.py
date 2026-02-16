#!/usr/bin/env python3
"""Check database schema and tables."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text, inspect
from app.database import get_async_session


async def check_schema():
    """Check database schema."""
    print("Checking database schema...")
    print()
    
    try:
        async for session in get_async_session():
            # Check if tables exist
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            
            tables = [row[0] for row in result.fetchall()]
            
            if not tables:
                print("❌ No tables found in database!")
                print("   Run: alembic upgrade head")
                return False
            
            print(f"✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"  - {table}")
            
            print()
            
            # Check if users table has new columns
            if 'users' in tables:
                result = await session.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'users'
                    AND column_name IN ('breedery_name', 'profile_image_path', 'breedery_description', 'search_tags')
                    ORDER BY column_name
                """))
                
                new_columns = list(result.fetchall())
                
                if new_columns:
                    print("✓ User profile columns found:")
                    for col in new_columns:
                        print(f"  - {col[0]} ({col[1]}, nullable: {col[2]})")
                else:
                    print("❌ User profile columns NOT found!")
                    print("   Run: alembic upgrade head")
                    return False
            
            print()
            
            # Check alembic version
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            
            print(f"✓ Alembic version: {version}")
            
            break
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(check_schema())
    sys.exit(0 if result else 1)
