"""Script to drop all tables and rerun migrations from scratch."""
import asyncio
from sqlalchemy import text
from app.database import async_session_maker, engine
from app.config import Settings

settings = Settings()

async def drop_all_tables():
    """Drop all tables in the database."""
    async with async_session_maker() as session:
        print("🗑️  Dropping all tables...")
        
        # Execute commands separately (asyncpg doesn't support multiple commands)
        await session.execute(text("DROP SCHEMA public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()
        
        print("✅ All tables dropped successfully")

async def main():
    """Main function."""
    print("=" * 60)
    print("DATABASE RESET")
    print("=" * 60)
    print(f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'unknown'}")
    print()
    
    # Confirm action
    response = input("⚠️  This will DELETE ALL DATA. Are you sure? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Aborted")
        return
    
    try:
        await drop_all_tables()
        print()
        print("✅ Database reset complete!")
        print()
        print("Next steps:")
        print("1. Run migrations: ./venv/bin/alembic upgrade head")
        print("2. Seed data if needed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
