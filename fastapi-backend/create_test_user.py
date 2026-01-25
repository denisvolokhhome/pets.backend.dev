"""
Create a test user for development
"""
import asyncio
import uuid
from app.database import get_async_session
from app.models.user import User
from fastapi_users.password import PasswordHelper

async def create_user():
    password_helper = PasswordHelper()
    
    # User details
    email = "davoloh@gmail.com"
    password = "testpassword123"  # Change this!
    name = "Test User"
    
    async for session in get_async_session():
        # Check if user exists
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"❌ User {email} already exists!")
            return
        
        # Create new user
        hashed_password = password_helper.hash(password)
        new_user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            is_verified=True,  # Auto-verify for testing
            name=name
        )
        
        session.add(new_user)
        await session.commit()
        
        print(f"✅ User created successfully!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Name: {name}")
        print(f"\n🔐 You can now login with these credentials")
        break

if __name__ == "__main__":
    asyncio.run(create_user())
