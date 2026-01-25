"""Property-based tests for profile image functionality."""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from typing import AsyncGenerator
import uuid
import os
from pathlib import Path
from io import BytesIO

from PIL import Image
from fastapi import UploadFile

from app.models.user import User
from app.database import Base
from app.services.file_service import FileService
from app.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with proper setup and teardown."""
    test_database_url = os.environ.get(
        'TEST_DATABASE_URL',
        'postgresql+asyncpg://test:test@localhost:5432/test_db'
    )
    
    engine = create_async_engine(
        test_database_url,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker_test = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker_test() as session:
        yield session
        await session.rollback()
    
    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
def file_service():
    """Create a FileService instance for testing."""
    settings = Settings()
    return FileService(settings)


@pytest.fixture
def temp_storage_path(tmp_path):
    """Create a temporary storage path for testing."""
    storage_path = tmp_path / "storage" / "app"
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def create_test_image(width: int = 100, height: int = 100, format: str = "JPEG") -> BytesIO:
    """Create a test image in memory."""
    image = Image.new('RGB', (width, height), color='red')
    buffer = BytesIO()
    image.save(buffer, format=format)
    buffer.seek(0)
    return buffer


async def create_upload_file(
    filename: str = "test.jpg",
    content_type: str = "image/jpeg",
    width: int = 100,
    height: int = 100
) -> UploadFile:
    """Create a mock UploadFile for testing."""
    from starlette.datastructures import Headers
    
    buffer = create_test_image(width, height)
    
    # Create UploadFile with headers containing content-type
    headers = Headers({"content-type": content_type})
    upload_file = UploadFile(
        filename=filename,
        file=buffer,
        headers=headers
    )
    
    return upload_file


class TestProfileImageFileCleanup:
    """
    Property 3: Profile Image File Cleanup
    
    For any user who uploads a new profile image, if a previous profile image exists,
    the old image file should be deleted from storage after the new image is 
    successfully saved.
    
    Validates: Requirements 9.7
    """
    
    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000
    )
    @given(
        num_uploads=st.integers(min_value=2, max_value=5)
    )
    async def test_old_image_deleted_on_new_upload(
        self,
        test_db_session: AsyncSession,
        file_service: FileService,
        num_uploads: int
    ):
        """
        Property test: When uploading multiple profile images sequentially,
        only the most recent image should exist in storage.
        
        Feature: user-profile-settings, Property 3: Profile Image File Cleanup
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        image_paths = []
        
        # Upload multiple images
        for i in range(num_uploads):
            # Create test image
            upload_file = await create_upload_file(
                filename=f"test_{i}.jpg",
                content_type="image/jpeg"
            )
            
            # Delete old image if exists
            if user.profile_image_path:
                old_path = user.profile_image_path
                try:
                    await file_service.delete_profile_image(old_path)
                except FileNotFoundError:
                    pass
            
            # Save new image
            image_path = await file_service.save_profile_image(upload_file, user.id)
            image_paths.append(image_path)
            
            # Update user
            user.profile_image_path = image_path
            await test_db_session.commit()
            await test_db_session.refresh(user)
        
        # Verify only the last image exists
        storage_path = Path(file_service.settings.storage_path).parent
        
        # Check that old images don't exist
        for old_path in image_paths[:-1]:
            full_path = storage_path / old_path
            assert not full_path.exists(), f"Old image {old_path} should have been deleted"
        
        # Check that the current image exists
        current_path = storage_path / image_paths[-1]
        assert current_path.exists(), f"Current image {image_paths[-1]} should exist"
        
        # Cleanup: delete the last image
        try:
            await file_service.delete_profile_image(image_paths[-1])
        except FileNotFoundError:
            pass
    
    @pytest.mark.asyncio
    async def test_image_cleanup_on_replacement(
        self,
        test_db_session: AsyncSession,
        file_service: FileService
    ):
        """
        Test that replacing a profile image deletes the old one.
        
        Feature: user-profile-settings, Property 3: Profile Image File Cleanup
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user
        user = User(
            email=f"replace_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Upload first image
        first_upload = await create_upload_file(filename="first.jpg")
        first_path = await file_service.save_profile_image(first_upload, user.id)
        user.profile_image_path = first_path
        await test_db_session.commit()
        
        # Verify first image exists
        storage_path = Path(file_service.settings.storage_path).parent
        first_full_path = storage_path / first_path
        assert first_full_path.exists()
        
        # Upload second image and delete first
        second_upload = await create_upload_file(filename="second.jpg")
        await file_service.delete_profile_image(first_path)
        second_path = await file_service.save_profile_image(second_upload, user.id)
        user.profile_image_path = second_path
        await test_db_session.commit()
        
        # Verify first image is deleted
        assert not first_full_path.exists(), "First image should be deleted"
        
        # Verify second image exists
        second_full_path = storage_path / second_path
        assert second_full_path.exists(), "Second image should exist"
        
        # Cleanup
        try:
            await file_service.delete_profile_image(second_path)
        except FileNotFoundError:
            pass
    
    @pytest.mark.asyncio
    async def test_no_error_when_old_image_missing(
        self,
        test_db_session: AsyncSession,
        file_service: FileService
    ):
        """
        Test that uploading a new image doesn't fail if the old image file is missing.
        
        Feature: user-profile-settings, Property 3: Profile Image File Cleanup
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user with a profile image path that doesn't exist
        user = User(
            email=f"missing_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            profile_image_path="storage/app/nonexistent_image.jpg"
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Try to delete the non-existent image (should raise FileNotFoundError)
        with pytest.raises(FileNotFoundError):
            await file_service.delete_profile_image(user.profile_image_path)
        
        # Upload new image should still work
        new_upload = await create_upload_file(filename="new.jpg")
        new_path = await file_service.save_profile_image(new_upload, user.id)
        user.profile_image_path = new_path
        await test_db_session.commit()
        
        # Verify new image exists
        storage_path = Path(file_service.settings.storage_path).parent
        new_full_path = storage_path / new_path
        assert new_full_path.exists()
        
        # Cleanup
        try:
            await file_service.delete_profile_image(new_path)
        except FileNotFoundError:
            pass
    
    @pytest.mark.asyncio
    async def test_concurrent_uploads_cleanup(
        self,
        test_db_session: AsyncSession,
        file_service: FileService
    ):
        """
        Test that multiple rapid uploads properly clean up old images.
        
        Feature: user-profile-settings, Property 3: Profile Image File Cleanup
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user
        user = User(
            email=f"concurrent_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        paths = []
        
        # Simulate 3 rapid uploads
        for i in range(3):
            upload = await create_upload_file(filename=f"rapid_{i}.jpg")
            
            # Delete old if exists
            if user.profile_image_path:
                try:
                    await file_service.delete_profile_image(user.profile_image_path)
                except FileNotFoundError:
                    pass
            
            # Save new
            path = await file_service.save_profile_image(upload, user.id)
            paths.append(path)
            user.profile_image_path = path
            await test_db_session.commit()
        
        # Verify only the last image exists
        storage_path = Path(file_service.settings.storage_path).parent
        
        for old_path in paths[:-1]:
            full_path = storage_path / old_path
            assert not full_path.exists(), f"Old image {old_path} should be deleted"
        
        current_path = storage_path / paths[-1]
        assert current_path.exists(), "Current image should exist"
        
        # Cleanup
        try:
            await file_service.delete_profile_image(paths[-1])
        except FileNotFoundError:
            pass
