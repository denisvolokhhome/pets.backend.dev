"""Verify that all existing users have is_breeder=True after migration."""
import asyncio
from sqlalchemy import select
from app.database import async_session_maker
from app.models.user import User


async def verify_user_types():
    """Check all users have is_breeder=True."""
    async with async_session_maker() as session:
        # Get all users
        result = await session.execute(select(User))
        users = result.scalars().all()
        
        print(f"\nTotal users in database: {len(users)}")
        
        if len(users) == 0:
            print("No users found in database.")
            return
        
        # Check each user
        breeder_count = 0
        pet_seeker_count = 0
        
        for user in users:
            if user.is_breeder:
                breeder_count += 1
            else:
                pet_seeker_count += 1
            print(f"User {user.email}: is_breeder={user.is_breeder}, oauth_provider={user.oauth_provider}")
        
        print(f"\nSummary:")
        print(f"  Breeders: {breeder_count}")
        print(f"  Pet Seekers: {pet_seeker_count}")
        
        # Verify all existing users are breeders
        if pet_seeker_count == 0:
            print("\n✓ Verification PASSED: All existing users have is_breeder=True")
        else:
            print(f"\n✗ Verification FAILED: {pet_seeker_count} users have is_breeder=False")


if __name__ == "__main__":
    asyncio.run(verify_user_types())
