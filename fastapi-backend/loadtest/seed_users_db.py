"""
Create verified load-test accounts directly in the database: no emails, no rate limits.

Use this on shared servers (dev/staging) instead of seed_users.py, which registers through
the API and so sends a welcome + verification email per account. Run it inside the backend
container, which already has DATABASE_URL:

    docker exec -i -e LOADTEST_PASSWORD='...' breedly-backend python - < loadtest/seed_users_db.py
    docker exec -i breedly-backend python - --cleanup < loadtest/seed_users_db.py   # remove them

Accounts are loadtest.seeker.N / loadtest.breeder.N @loadtest.breedly.dev, matching
accounts.json. Re-running is safe: existing accounts are kept. --cleanup deletes every
@loadtest.breedly.dev user; all foreign keys to users cascade.
Never run against production.
"""
import asyncio
import os
import sys

from fastapi_users.password import PasswordHelper
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.user import User

DOMAIN = "loadtest.breedly.dev"
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "LoadTest2026!")
SEEKERS = int(os.environ.get("LOADTEST_SEEKERS", "40"))
BREEDERS = int(os.environ.get("LOADTEST_BREEDERS", "10"))


async def seed() -> None:
    hashed = PasswordHelper().hash(PASSWORD)  # one hash for all: argon2/bcrypt is slow
    wanted = [(f"loadtest.seeker.{i}@{DOMAIN}", False, f"Load Seeker {i}") for i in range(SEEKERS)]
    wanted += [(f"loadtest.breeder.{i}@{DOMAIN}", True, f"Load Breeder {i}") for i in range(BREEDERS)]

    async with async_session_maker() as session:
        existing = set((await session.execute(
            select(User.email).where(User.email.like(f"%@{DOMAIN}"))
        )).scalars())
        new_breeders = []
        for email, is_breeder, name in wanted:
            if email in existing:
                continue
            user = User(
                email=email, hashed_password=hashed, name=name,
                is_active=True, is_verified=True, is_breeder=is_breeder,
                account_type="breeder" if is_breeder else "pet_seeker",
                breedery_name=name if is_breeder else None,
            )
            session.add(user)
            if is_breeder:
                new_breeders.append(user)
        await session.commit()

        # Breeders get the FREE plan on registration; mirror that so billing views behave
        from app.services.billing_service import billing_service
        for user in new_breeders:
            try:
                await billing_service.create_default_subscription(session, user.id)
            except Exception as exc:  # noqa: BLE001 — plans may not be seeded on this server
                await session.rollback()
                print(f"  no default subscription for {user.email}: {exc}")
        await session.commit()

    created = len(wanted) - len(existing & {e for e, _, _ in wanted})
    print(f"{created} created, {len(wanted) - created} already existed ({SEEKERS} seekers, {BREEDERS} breeders)")


async def cleanup() -> None:
    async with async_session_maker() as session:
        result = await session.execute(delete(User).where(User.email.like(f"%@{DOMAIN}")))
        await session.commit()
    print(f"deleted {result.rowcount} load-test users (and their rows, via ON DELETE CASCADE)")


if __name__ == "__main__":
    asyncio.run(cleanup() if "--cleanup" in sys.argv else seed())
