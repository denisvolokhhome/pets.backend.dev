"""Verify the database schema has the new columns and indexes."""
import asyncio
from sqlalchemy import text
from app.database import async_session_maker


async def verify_schema():
    """Check that the new columns and indexes exist."""
    async with async_session_maker() as session:
        # Check columns exist
        print("Checking columns in users table...")
        result = await session.execute(text("""
            SELECT column_name, data_type, column_default, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name IN ('is_breeder', 'oauth_provider', 'oauth_id')
            ORDER BY column_name;
        """))
        columns = result.fetchall()
        
        print("\nColumns found:")
        for col in columns:
            print(f"  - {col[0]}: {col[1]}, default={col[2]}, nullable={col[3]}")
        
        # Check indexes exist
        print("\nChecking indexes on users table...")
        result = await session.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'users'
            AND indexname IN ('ix_users_is_breeder', 'ix_users_oauth_id')
            ORDER BY indexname;
        """))
        indexes = result.fetchall()
        
        print("\nIndexes found:")
        for idx in indexes:
            print(f"  - {idx[0]}")
            print(f"    Definition: {idx[1]}")
        
        # Verify expected columns
        expected_columns = {'is_breeder', 'oauth_provider', 'oauth_id'}
        found_columns = {col[0] for col in columns}
        
        if expected_columns == found_columns:
            print("\n✓ All expected columns exist")
        else:
            missing = expected_columns - found_columns
            print(f"\n✗ Missing columns: {missing}")
        
        # Verify expected indexes
        expected_indexes = {'ix_users_is_breeder', 'ix_users_oauth_id'}
        found_indexes = {idx[0] for idx in indexes}
        
        if expected_indexes == found_indexes:
            print("✓ All expected indexes exist")
        else:
            missing = expected_indexes - found_indexes
            print(f"✗ Missing indexes: {missing}")


if __name__ == "__main__":
    asyncio.run(verify_schema())
