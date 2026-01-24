"""Unit tests for FileService."""

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile
from PIL import Image

from app.config import Settings
from app.services.file_service import FileService


@pytest.fixture
def test_settings(tmp_path):
    """Create test settings with temporary storage path."""
    settings = Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        secret_key="test_secret_key_at_least_32_characters_long",
        storage_path=str(tmp_path / "storage" / "app"),
        storage_url="/storage",
        max_image_size_mb=5,
        allowed_image_types="image/jpeg,image/png,image/webp",
        image_max_width=1920,
        image_max_height=1920,
        image_quality=85,
    )
    return settings


@pytest.fixture
def file_service(test_settings):
    """Create FileService instance with test settings."""
    return FileService(test_settings)


@pytest.fixture
def create_test_image():
    """Factory fixture to create test images."""
    def _create_image(width=800, height=600, format="JPEG", mode="RGB"):
        """Create a test image in memory."""
        image = Image.new(mode, (width, height), color=(255, 0, 0))
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=format)
        img_bytes.seek(0)
        return img_bytes

    return _create_image


@pytest.fixture
def create_upload_file(create_test_image):
    """Factory fixture to create UploadFile instances."""
    def _create_upload_file(
        filename="test.jpg",
        content_type="image/jpeg",
        width=800,
        height=600,
        format="JPEG",
        mode="RGB"
    ):
        """Create an UploadFile with test image."""
        img_bytes = create_test_image(width, height, format, mode)
        # Create UploadFile with headers to set content_type
        from starlette.datastructures import Headers
        headers = Headers({"content-type": content_type})
        upload_file = UploadFile(filename=filename, file=img_bytes, headers=headers)
        return upload_file

    return _create_upload_file


class TestFileServiceInit:
    """Tests for FileService initialization."""

    def test_init_creates_storage_directory(self, test_settings):
        """Test that FileService creates storage directory on init."""
        service = FileService(test_settings)
        assert service.storage_path.exists()
        assert service.storage_path.is_dir()

    def test_init_sets_configuration(self, test_settings, file_service):
        """Test that FileService correctly sets configuration from settings."""
        assert file_service.settings == test_settings
        assert file_service.max_size == test_settings.max_image_size_bytes
        assert file_service.max_width == test_settings.image_max_width
        assert file_service.max_height == test_settings.image_max_height
        assert file_service.quality == test_settings.image_quality
        assert file_service.allowed_types == test_settings.get_allowed_image_types_list()


class TestSaveImage:
    """Tests for save_image method."""

    @pytest.mark.asyncio
    async def test_save_image_with_valid_jpeg(self, file_service, create_upload_file):
        """Test saving a valid JPEG image."""
        pet_id = uuid.uuid4()
        upload_file = create_upload_file(filename="test.jpg", content_type="image/jpeg")

        image_path, original_filename = await file_service.save_image(upload_file, pet_id)

        # Verify return values
        assert image_path.startswith("app/")  # Relative to storage parent
        assert original_filename == "test.jpg"

        # Verify file was created
        full_path = file_service.storage_path.parent / image_path
        assert full_path.exists()
        assert full_path.is_file()

        # Verify it's a valid image
        img = Image.open(full_path)
        assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_save_image_with_valid_png(self, file_service, create_upload_file):
        """Test saving a valid PNG image."""
        pet_id = uuid.uuid4()
        upload_file = create_upload_file(
            filename="test.png",
            content_type="image/png",
            format="PNG"
        )

        image_path, original_filename = await file_service.save_image(upload_file, pet_id)

        # Verify return values
        assert image_path.startswith("app/")  # Relative to storage parent
        assert original_filename == "test.png"

        # Verify file was created
        full_path = file_service.storage_path.parent / image_path
        assert full_path.exists()

    @pytest.mark.asyncio
    async def test_save_image_rejects_non_image_content_type(self, file_service):
        """Test that non-image content types are rejected."""
        from starlette.datastructures import Headers
        pet_id = uuid.uuid4()
        headers = Headers({"content-type": "text/plain"})
        upload_file = UploadFile(filename="test.txt", file=io.BytesIO(b"not an image"), headers=headers)

        with pytest.raises(ValueError, match="Invalid file type"):
            await file_service.save_image(upload_file, pet_id)

    @pytest.mark.asyncio
    async def test_save_image_rejects_oversized_file(self, file_service, create_test_image):
        """Test that files exceeding size limit are rejected."""
        from starlette.datastructures import Headers
        pet_id = uuid.uuid4()

        # Create a large image that exceeds the 5MB limit
        # Create a very large image (3000x3000 should be > 5MB uncompressed)
        large_image = Image.new("RGB", (3000, 3000), color=(255, 0, 0))
        img_bytes = io.BytesIO()
        large_image.save(img_bytes, format="PNG", compress_level=0)  # No compression
        img_bytes.seek(0)

        # Make it definitely over 5MB
        file_size = len(img_bytes.getvalue())
        if file_size < 5 * 1024 * 1024:
            # Pad with extra data to ensure it's over 5MB
            padding = b"0" * (5 * 1024 * 1024 - file_size + 1000)
            img_bytes = io.BytesIO(img_bytes.getvalue() + padding)

        headers = Headers({"content-type": "image/png"})
        upload_file = UploadFile(filename="large.png", file=img_bytes, headers=headers)

        with pytest.raises(ValueError, match="exceeds maximum allowed size"):
            await file_service.save_image(upload_file, pet_id)

    @pytest.mark.asyncio
    async def test_save_image_rejects_invalid_image_data(self, file_service):
        """Test that invalid image data is rejected."""
        from starlette.datastructures import Headers
        pet_id = uuid.uuid4()
        headers = Headers({"content-type": "image/jpeg"})
        upload_file = UploadFile(filename="fake.jpg", file=io.BytesIO(b"not a real image"), headers=headers)

        with pytest.raises(ValueError, match="Invalid image file|not a valid image"):
            await file_service.save_image(upload_file, pet_id)

    @pytest.mark.asyncio
    async def test_save_image_resizes_large_image(self, file_service, create_upload_file):
        """Test that images larger than max dimensions are resized."""
        pet_id = uuid.uuid4()
        # Create image larger than max dimensions (1920x1920)
        upload_file = create_upload_file(
            filename="large.jpg",
            content_type="image/jpeg",
            width=3000,
            height=2500
        )

        image_path, _ = await file_service.save_image(upload_file, pet_id)

        # Verify image was resized
        full_path = file_service.storage_path.parent / image_path
        img = Image.open(full_path)
        assert img.width <= 1920
        assert img.height <= 1920

    @pytest.mark.asyncio
    async def test_save_image_generates_unique_filename(self, file_service, create_upload_file):
        """Test that each saved image gets a unique filename."""
        pet_id = uuid.uuid4()
        upload_file1 = create_upload_file(filename="test.jpg")
        upload_file2 = create_upload_file(filename="test.jpg")

        path1, _ = await file_service.save_image(upload_file1, pet_id)
        path2, _ = await file_service.save_image(upload_file2, pet_id)

        # Paths should be different
        assert path1 != path2

        # Both files should exist
        assert (file_service.storage_path.parent / path1).exists()
        assert (file_service.storage_path.parent / path2).exists()

    @pytest.mark.asyncio
    async def test_save_image_converts_rgba_to_rgb(self, file_service, create_upload_file):
        """Test that RGBA images are converted to RGB for JPEG."""
        pet_id = uuid.uuid4()
        upload_file = create_upload_file(
            filename="transparent.png",
            content_type="image/png",
            format="PNG",
            mode="RGBA"
        )

        image_path, _ = await file_service.save_image(upload_file, pet_id)

        # Verify image was saved and converted
        full_path = file_service.storage_path.parent / image_path
        img = Image.open(full_path)
        assert img.mode == "RGB"


class TestDeleteImage:
    """Tests for delete_image method."""

    @pytest.mark.asyncio
    async def test_delete_image_removes_file(self, file_service, create_upload_file):
        """Test that delete_image removes the file from storage."""
        pet_id = uuid.uuid4()
        upload_file = create_upload_file()

        # Save image first
        image_path, _ = await file_service.save_image(upload_file, pet_id)
        full_path = file_service.storage_path.parent / image_path
        assert full_path.exists()

        # Delete image
        await file_service.delete_image(image_path)

        # Verify file was deleted
        assert not full_path.exists()

    @pytest.mark.asyncio
    async def test_delete_image_raises_error_for_nonexistent_file(self, file_service):
        """Test that deleting non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Image file not found"):
            await file_service.delete_image("storage/app/nonexistent.jpg")


class TestGetImageUrl:
    """Tests for get_image_url method."""

    def test_get_image_url_returns_correct_url(self, file_service):
        """Test that get_image_url generates correct public URL."""
        image_path = "storage/app/test_image.jpg"
        url = file_service.get_image_url(image_path)

        assert url == "/storage/app/test_image.jpg"

    def test_get_image_url_handles_none(self, file_service):
        """Test that get_image_url returns None for None input."""
        url = file_service.get_image_url(None)
        assert url is None

    def test_get_image_url_handles_empty_string(self, file_service):
        """Test that get_image_url returns None for empty string."""
        url = file_service.get_image_url("")
        assert url is None

    def test_get_image_url_normalizes_path_separators(self, file_service):
        """Test that get_image_url converts backslashes to forward slashes."""
        image_path = "storage\\app\\test_image.jpg"
        url = file_service.get_image_url(image_path)

        assert "\\" not in url
        assert url == "/storage/app/test_image.jpg"

    def test_get_image_url_removes_duplicate_storage_prefix(self, file_service):
        """Test that get_image_url doesn't duplicate storage prefix."""
        image_path = "storage/app/test_image.jpg"
        url = file_service.get_image_url(image_path)

        # Should not have double 'storage'
        assert url == "/storage/app/test_image.jpg"
        assert url.count("storage") == 1
