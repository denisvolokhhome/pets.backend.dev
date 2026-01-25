import asyncio
from app.database import engine
from sqlalchemy import inspect

async def check_tables():
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        print(f"Tables in database: {tables}")
        if not tables:
            print("\n⚠️  Database is empty! No tables found.")
            print("You need to run migrations: alembic upgrade head")
        else:
            print(f"\n✅ Found {len(tables)} tables")

if __name__ == "__main__":
    asyncio.run(check_tables())
