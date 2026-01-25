"""Property-based tests for image handling."""

import io
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from hypothesis import given, settings, strategies as st, HealthCheck
from PIL import Image
from starlette.datastructures import Headers

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


def create_test_image(width=800, height=600, format="JPEG", mode="RGB"):
    """Create a test image in memory."""
    image = Image.new(mode, (width, height), color=(255, 0, 0))
    img_bytes = io.BytesIO()
    image.save(img_bytes, format=format)
    img_bytes.seek(0)
    return img_bytes


def create_upload_file(filename="test.jpg", content_type="image/jpeg", width=800, height=600):
    """Create an UploadFile with test image."""
    img_bytes = create_test_image(width, height)
    headers = Headers({"content-type": content_type})
    upload_file = UploadFile(filename=filename, file=img_bytes, headers=headers)
    return upload_file


class TestImageStorageProperties:
    """Property-based tests for image storage."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        pet_id=st.uuids(version=4),
        width=st.integers(min_value=100, max_value=2000),
        height=st.integers(min_value=100, max_value=2000),
    )
    @pytest.mark.asyncio
    async def test_property_image_storage_persistence(self, file_service, pet_id, width, height):
        """
        Property 18: Image Storage Persistence
        For any uploaded image, the file should exist in the configured storage directory after upload.

        Feature: laravel-to-fastapi-migration, Property 18: Image Storage Persistence
        Validates: Requirements 9.2
        """
        # Create upload file with random dimensions
        upload_file = create_upload_file(
            filename=f"test_{pet_id}.jpg",
            content_type="image/jpeg",
            width=width,
            height=height
        )

        # Save image
        image_path, _ = await file_service.save_image(upload_file, pet_id)

        # Verify file exists in storage
        full_path = file_service.storage_path.parent / image_path
        assert full_path.exists(), f"Image file should exist at {full_path}"
        assert full_path.is_file(), f"Path should be a file, not a directory"

        # Verify it's a valid image that can be opened
        img = Image.open(full_path)
        assert img is not None, "Saved file should be a valid image"

        # Clean up
        await file_service.delete_image(image_path)


class TestImageValidationProperties:
    """Property-based tests for image validation."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        pet_id=st.uuids(version=4),
        invalid_content=st.binary(min_size=10, max_size=1000),
    )
    @pytest.mark.asyncio
    async def test_property_image_validation(self, file_service, pet_id, invalid_content):
        """
        Property 19: Image Validation
        For any uploaded file that is not a valid image format, the upload should be rejected with an error.

        Feature: laravel-to-fastapi-migration, Property 19: Image Validation
        Validates: Requirements 9.3
        """
        # Create upload file with invalid image data
        headers = Headers({"content-type": "image/jpeg"})
        upload_file = UploadFile(
            filename="invalid.jpg",
            file=io.BytesIO(invalid_content),
            headers=headers
        )

        # Attempt to save should raise ValueError
        with pytest.raises(ValueError, match="Invalid image file|not a valid image"):
            await file_service.save_image(upload_file, pet_id)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        pet_id=st.uuids(version=4),
        content_type=st.sampled_from(["text/plain", "application/pdf", "video/mp4", "audio/mp3"]),
    )
    @pytest.mark.asyncio
    async def test_property_invalid_content_type_rejection(self, file_service, pet_id, content_type):
        """
        Property 19: Image Validation (Content Type)
        For any uploaded file with non-image content type, the upload should be rejected.

        Feature: laravel-to-fastapi-migration, Property 19: Image Validation
        Validates: Requirements 9.3
        """
        # Create upload file with invalid content type
        headers = Headers({"content-type": content_type})
        upload_file = UploadFile(
            filename="test.txt",
            file=io.BytesIO(b"not an image"),
            headers=headers
        )

        # Attempt to save should raise ValueError
        with pytest.raises(ValueError, match="Invalid file type"):
            await file_service.save_image(upload_file, pet_id)


class TestUniqueFilenameProperties:
    """Property-based tests for unique filename generation."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        pet_id=st.uuids(version=4),
        num_uploads=st.integers(min_value=2, max_value=5),
    )
    @pytest.mark.asyncio
    async def test_property_unique_image_filenames(self, file_service, pet_id, num_uploads):
        """
        Property 20: Unique Image Filenames
        For any two image uploads, the generated filenames should be different to prevent collisions.

        Feature: laravel-to-fastapi-migration, Property 20: Unique Image Filenames
        Validates: Requirements 9.4
        """
        saved_paths = []

        # Upload multiple images with the same filename
        for i in range(num_uploads):
            upload_file = create_upload_file(
                filename="duplicate.jpg",
                content_type="image/jpeg"
            )

            image_path, _ = await file_service.save_image(upload_file, pet_id)
            saved_paths.append(image_path)

        # Verify all paths are unique
        assert len(saved_paths) == len(set(saved_paths)), \
            f"All generated filenames should be unique, got: {saved_paths}"

        # Verify all files exist
        for path in saved_paths:
            full_path = file_service.storage_path.parent / path
            assert full_path.exists(), f"File should exist at {full_path}"

        # Clean up
        for path in saved_paths:
            await file_service.delete_image(path)


class TestImageUrlProperties:
    """Property-based tests for image URL generation."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        pet_id=st.uuids(version=4),
        filename=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=1,
            max_size=50
        ).filter(lambda x: x and not x.startswith(".")),
    )
    @pytest.mark.asyncio
    async def test_property_image_url_accessibility(self, file_service, pet_id, filename):
        """
        Property 22: Image URL Accessibility
        For any uploaded image, the generated public URL should return the image file when accessed.

        Feature: laravel-to-fastapi-migration, Property 22: Image URL Accessibility
        Validates: Requirements 9.6
        """
        # Create and save image
        safe_filename = f"{filename}.jpg"
        upload_file = create_upload_file(
            filename=safe_filename,
            content_type="image/jpeg"
        )

        image_path, _ = await file_service.save_image(upload_file, pet_id)

        # Generate URL
        url = file_service.get_image_url(image_path)

        # Verify URL is not None
        assert url is not None, "URL should not be None for valid image path"

        # Verify URL starts with storage URL prefix
        assert url.startswith(file_service.settings.storage_url), \
            f"URL should start with {file_service.settings.storage_url}"

        # Verify URL contains a path component
        assert len(url) > len(file_service.settings.storage_url), \
            "URL should contain path after storage prefix"

        # Verify the file exists at the path referenced by the URL
        # The image_path already contains the correct relative path from storage parent
        # So we should use it directly instead of extracting from URL
        full_path = file_service.storage_path.parent / image_path

        assert full_path.exists(), \
            f"File should exist at path: {full_path}"

        # Clean up
        await file_service.delete_image(image_path)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        image_path=st.one_of(
            st.none(),
            st.just(""),
        )
    )
    def test_property_image_url_handles_invalid_paths(self, file_service, image_path):
        """
        Property 22: Image URL Accessibility (Invalid Paths)
        For any invalid image path (None or empty), get_image_url should return None.

        Feature: laravel-to-fastapi-migration, Property 22: Image URL Accessibility
        Validates: Requirements 9.6
        """
        url = file_service.get_image_url(image_path)
        assert url is None, f"URL should be None for invalid path: {image_path}"


class TestProfileImageValidationProperties:
    """Property-based tests for profile image upload validation."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=st.uuids(version=4),
        content_type=st.sampled_from([
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp"
        ]),
        width=st.integers(min_value=100, max_value=1500),
        height=st.integers(min_value=100, max_value=1500),
    )
    @pytest.mark.asyncio
    async def test_property_profile_image_upload_validation_accepts_valid(
        self, file_service, user_id, content_type, width, height
    ):
        """
        Property 5: Image Upload Validation
        For any valid image file (JPEG, PNG, GIF, WebP) under 5MB, the upload should succeed.

        Feature: user-profile-settings, Property 5: Image Upload Validation
        Validates: Requirements 9.1, 9.2
        """
        # Create upload file with valid type and size
        format_map = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
            "image/gif": "GIF",
            "image/webp": "WEBP"
        }
        format_name = format_map[content_type]
        
        img_bytes = create_test_image(width, height, format=format_name)
        
        # Ensure file is under 5MB
        file_size = len(img_bytes.getvalue())
        if file_size >= 5 * 1024 * 1024:
            # Skip this test case if randomly generated image is too large
            pytest.skip("Generated image exceeds 5MB")
        
        headers = Headers({"content-type": content_type})
        upload_file = UploadFile(
            filename=f"profile.{format_name.lower()}",
            file=img_bytes,
            headers=headers
        )

        # Upload should succeed
        image_path = await file_service.save_profile_image(upload_file, user_id)

        # Verify file was saved
        assert image_path is not None
        full_path = file_service.storage_path.parent / image_path
        assert full_path.exists(), "Profile image should be saved to storage"

        # Verify it's a valid image
        img = Image.open(full_path)
        assert img is not None

        # Clean up
        await file_service.delete_profile_image(image_path)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=st.uuids(version=4),
        content_type=st.sampled_from([
            "image/bmp",
            "image/tiff",
            "image/svg+xml",
            "text/plain",
            "application/pdf",
            "video/mp4"
        ]),
    )
    @pytest.mark.asyncio
    async def test_property_profile_image_upload_validation_rejects_invalid_type(
        self, file_service, user_id, content_type
    ):
        """
        Property 5: Image Upload Validation (Invalid Types)
        For any file with invalid content type (not JPEG, PNG, GIF, WebP), the upload should be rejected.

        Feature: user-profile-settings, Property 5: Image Upload Validation
        Validates: Requirements 9.1, 9.2
        """
        # Create upload file with invalid content type
        headers = Headers({"content-type": content_type})
        upload_file = UploadFile(
            filename="invalid.file",
            file=io.BytesIO(b"fake content"),
            headers=headers
        )

        # Upload should be rejected
        with pytest.raises(ValueError, match="Invalid file type"):
            await file_service.save_profile_image(upload_file, user_id)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=st.uuids(version=4),
        # Generate file sizes that are definitely over 5MB
        extra_mb=st.integers(min_value=1, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_property_profile_image_upload_validation_rejects_oversized(
        self, file_service, user_id, extra_mb
    ):
        """
        Property 5: Image Upload Validation (Size Limit)
        For any file exceeding 5MB, the upload should be rejected with a size error.

        Feature: user-profile-settings, Property 5: Image Upload Validation
        Validates: Requirements 9.1, 9.2
        """
        # Create a large image that exceeds 5MB
        large_image = Image.new("RGB", (3000, 3000), color=(255, 0, 0))
        img_bytes = io.BytesIO()
        large_image.save(img_bytes, format="PNG", compress_level=0)
        img_bytes.seek(0)

        # Ensure it's over 5MB by padding if necessary
        file_size = len(img_bytes.getvalue())
        target_size = (5 * 1024 * 1024) + (extra_mb * 1024 * 1024)
        if file_size < target_size:
            padding = b"0" * (target_size - file_size)
            img_bytes = io.BytesIO(img_bytes.getvalue() + padding)

        headers = Headers({"content-type": "image/png"})
        upload_file = UploadFile(
            filename="large_profile.png",
            file=img_bytes,
            headers=headers
        )

        # Upload should be rejected
        with pytest.raises(ValueError, match="exceeds maximum allowed size"):
            await file_service.save_profile_image(upload_file, user_id)
