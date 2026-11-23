"""File service for handling image and document uploads.

Files live in object storage (RustFS): images in the photos bucket under
"<upload dir name>/<file>" (the same path stored in the DB and used in
/storage/... URLs), documents in the private documents bucket.
"""

import asyncio
import io
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.config import Settings
from app.services.object_storage import (
    ObjectNotFoundError,
    documents_bucket,
    get_object_storage,
    photos_bucket,
)


def _encode_image(image: Image.Image, filename: str, quality: int, fmt: Optional[str] = None) -> Tuple[bytes, str]:
    """Encode an image the way Image.save(path) would, returning (bytes, content type)."""
    fmt = fmt or Image.registered_extensions().get(Path(filename).suffix.lower(), "JPEG")
    kwargs = {"optimize": True}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = quality
    buf = io.BytesIO()
    image.save(buf, format=fmt, **kwargs)
    return buf.getvalue(), Image.MIME.get(fmt, "application/octet-stream")


class FileService:
    """Service for handling file uploads, particularly pet images."""

    # Profile image specific constants
    ALLOWED_PROFILE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_PROFILE_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

    def __init__(self, settings: Settings):
        """
        Initialize FileService with configuration.

        Args:
            settings: Application settings containing storage configuration
        """
        self.settings = settings
        # Only used to build keys and to read pre-migration local copies; never written.
        self.storage_path = Path(settings.storage_path)
        self.key_prefix = self.storage_path.name
        self.storage = get_object_storage()
        self.allowed_types = settings.get_allowed_image_types_list()
        self.max_size = settings.max_image_size_bytes
        self.max_width = settings.image_max_width
        self.max_height = settings.image_max_height
        self.quality = settings.image_quality

    async def save_image(
        self,
        file: UploadFile,
        pet_id: uuid.UUID,
    ) -> Tuple[str, str]:
        """
        Save uploaded image and return (image_path, image_file_name).

        Args:
            file: Uploaded file from FastAPI
            pet_id: UUID of the pet this image belongs to

        Returns:
            Tuple of (relative_path, original_filename)

        Raises:
            ValueError: If file is not a valid image or exceeds size limits
        """
        # Validate content type
        if file.content_type not in self.allowed_types:
            raise ValueError(
                f"Invalid file type. Allowed types: {', '.join(self.allowed_types)}"
            )

        # Read file contents
        contents = await file.read()

        # Validate file size
        if len(contents) > self.max_size:
            size_mb = len(contents) / (1024 * 1024)
            max_mb = self.max_size / (1024 * 1024)
            raise ValueError(
                f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_mb}MB)"
            )

        # Validate and process image
        try:
            image = Image.open(io.BytesIO(contents))
        except Exception as e:
            raise ValueError(f"Invalid image file: {str(e)}")

        # Verify it's actually an image
        try:
            image.verify()
            # Reopen after verify (verify closes the file)
            image = Image.open(io.BytesIO(contents))
        except Exception as e:
            raise ValueError(f"File is not a valid image: {str(e)}")

        # Phone photos store rotation in EXIF, which is dropped on save: bake it in.
        image = ImageOps.exif_transpose(image)

        # Generate unique filename
        ext = Path(file.filename).suffix if file.filename else ".jpg"
        if not ext:
            ext = ".jpg"
        filename = f"{pet_id}_{uuid.uuid4()}{ext}"

        # Resize if needed (maintain aspect ratio)
        max_size = (self.max_width, self.max_height)
        if image.width > max_size[0] or image.height > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert RGBA to RGB if necessary (for JPEG)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = background

        # Save processed image
        relative_path = await self._put_image(image, filename)
        original_filename = file.filename or filename

        return relative_path, original_filename

    # Clockwise degrees -> Pillow transpose (Pillow's ROTATE_* are counter-clockwise).
    _ROTATIONS = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }

    async def _put_image(self, image: Image.Image, filename: str, fmt: Optional[str] = None) -> str:
        """Store an encoded image in the photos bucket and return its key."""
        data, content_type = _encode_image(image, filename, self.quality, fmt)
        key = f"{self.key_prefix}/{filename}"
        await asyncio.to_thread(self.storage.put, photos_bucket(), key, data, content_type)
        return key

    def _local_copy(self, key: str) -> Optional[Path]:
        """Pre-migration local file for a stored key, if it still exists inside STORAGE_PATH."""
        if "\\" in key or ".." in key.split("/"):
            return None
        root = self.storage_path.resolve()
        path = (self.storage_path.parent / key).resolve()
        return path if root in path.parents and path.is_file() else None

    async def _read_photo(self, key: str) -> bytes:
        try:
            return (await asyncio.to_thread(self.storage.get, photos_bucket(), key)).data
        except ObjectNotFoundError:
            local = self._local_copy(key)
            if local is None:
                raise FileNotFoundError(f"Image file not found: {key}") from None
            return local.read_bytes()

    async def _delete_photo(self, key: str, missing_message: str) -> None:
        in_bucket = await asyncio.to_thread(self.storage.exists, photos_bucket(), key)
        local = self._local_copy(key)
        if not in_bucket and local is None:
            raise FileNotFoundError(missing_message)
        if in_bucket:
            await asyncio.to_thread(self.storage.delete, photos_bucket(), key)
        if local is not None:
            local.unlink(missing_ok=True)

    async def rotate_image(self, image_path: str, degrees: int) -> str:
        """
        Rotate a stored image clockwise by 90, 180 or 270 degrees.

        The result is written under a new key so browsers and CDNs don't keep
        showing the cached original; the old image is removed.

        Returns:
            New relative path (key) of the rotated image.

        Raises:
            ValueError: unsupported angle or invalid path
            FileNotFoundError: the stored image is missing
        """
        degrees = degrees % 360
        if degrees not in self._ROTATIONS:
            raise ValueError("Rotation must be 90, 180 or 270 degrees")
        if "\\" in image_path or ".." in image_path.split("/"):
            raise ValueError("Invalid image path")

        data = await self._read_photo(image_path)
        with Image.open(io.BytesIO(data)) as opened:
            fmt = opened.format
            image = ImageOps.exif_transpose(opened).transpose(self._ROTATIONS[degrees])

        src = Path(image_path)
        prefix = src.stem.rsplit("_", 1)[0] if "_" in src.stem else src.stem
        new_key = await self._put_image(image, f"{prefix}_{uuid.uuid4()}{src.suffix}", fmt)
        await self._delete_photo(image_path, f"Image file not found: {image_path}")
        return new_key

    async def delete_image(self, image_path: str) -> None:
        """
        Delete an image from storage.

        Raises:
            FileNotFoundError: If the image does not exist
        """
        await self._delete_photo(image_path, f"Image file not found: {image_path}")

    def get_image_url(self, image_path: Optional[str]) -> Optional[str]:
        """
        Generate public URL for image.

        Args:
            image_path: Relative path to the image file

        Returns:
            Public URL for the image, or None if image_path is None
        """
        if not image_path:
            return None

        # Convert path to use forward slashes for URLs
        url_path = image_path.replace("\\", "/")

        # Remove 'storage/' prefix if present to avoid duplication
        if url_path.startswith("storage/"):
            url_path = url_path[8:]  # Remove 'storage/' prefix

        return f"{self.settings.storage_url}/{url_path}"

    async def save_profile_image(
        self,
        file: UploadFile,
        user_id: uuid.UUID,
    ) -> str:
        """
        Save uploaded profile image and return relative path.

        Args:
            file: Uploaded file from FastAPI
            user_id: UUID of the user this profile image belongs to

        Returns:
            Relative path to the saved image

        Raises:
            ValueError: If file is not a valid image or exceeds size limits
        """
        # Validate content type
        if file.content_type not in self.ALLOWED_PROFILE_IMAGE_TYPES:
            raise ValueError(
                f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_PROFILE_IMAGE_TYPES)}"
            )

        # Read file contents
        contents = await file.read()

        # Validate file size
        if len(contents) > self.MAX_PROFILE_IMAGE_SIZE:
            size_mb = len(contents) / (1024 * 1024)
            max_mb = self.MAX_PROFILE_IMAGE_SIZE / (1024 * 1024)
            raise ValueError(
                f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_mb}MB)"
            )

        # Validate and process image
        try:
            image = Image.open(io.BytesIO(contents))
        except Exception as e:
            raise ValueError(f"Invalid image file: {str(e)}")

        # Verify it's actually an image
        try:
            image.verify()
            # Reopen after verify (verify closes the file)
            image = Image.open(io.BytesIO(contents))
        except Exception as e:
            raise ValueError(f"File is not a valid image: {str(e)}")

        # Phone photos store rotation in EXIF, which is dropped on save: bake it in.
        image = ImageOps.exif_transpose(image)

        # Generate unique filename for profile image
        ext = Path(file.filename).suffix if file.filename else ".jpg"
        if not ext:
            ext = ".jpg"
        filename = f"profile_{user_id}_{uuid.uuid4()}{ext}"

        # Resize if needed (maintain aspect ratio)
        # Use smaller dimensions for profile images
        max_size = (800, 800)
        if image.width > max_size[0] or image.height > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert RGBA to RGB if necessary (for JPEG)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = background

        # Save processed image
        return await self._put_image(image, filename)

    async def delete_profile_image(self, image_path: str) -> None:
        """
        Delete profile image file from storage.

        Args:
            image_path: Relative path to the profile image file

        Raises:
            FileNotFoundError: If image file does not exist
        """
        await self._delete_photo(image_path, f"Profile image file not found: {image_path}")

    async def read_photo(self, image_path: str) -> Tuple[bytes, str]:
        """Bytes and content type of a stored image (FileNotFoundError if missing)."""
        data = await self._read_photo(image_path)
        fmt = Image.registered_extensions().get(Path(image_path).suffix.lower(), "JPEG")
        return data, Image.MIME.get(fmt, "application/octet-stream")
    ALLOWED_DOCUMENT_TYPES = {
        "application/pdf",
        "image/jpeg", "image/png", "image/gif", "image/webp",
    }
    MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB

    async def save_document(
        self,
        file: UploadFile,
        pet_id: uuid.UUID,
    ) -> Tuple[str, str, str, int]:
        """
        Save uploaded document (PDF or image) and return metadata.

        Returns:
            Tuple of (storage key, original_filename, content_type, file_size)
        """
        if file.content_type not in self.ALLOWED_DOCUMENT_TYPES:
            raise ValueError(
                f"Invalid file type. Allowed: PDF, JPEG, PNG, GIF, WebP"
            )

        contents = await file.read()

        if len(contents) > self.MAX_DOCUMENT_SIZE:
            size_mb = len(contents) / (1024 * 1024)
            raise ValueError(f"File size ({size_mb:.1f}MB) exceeds 10MB limit")

        ext = Path(file.filename).suffix if file.filename else ".pdf"
        if not ext:
            ext = ".pdf"
        key = f"doc_{pet_id}_{uuid.uuid4()}{ext}"
        await asyncio.to_thread(self.storage.put, documents_bucket(), key, contents, file.content_type)
        original_filename = file.filename or key

        return key, original_filename, file.content_type, len(contents)

    async def delete_document(self, file_path: str) -> None:
        """Delete a document from the documents bucket (missing is fine)."""
        await asyncio.to_thread(self.storage.delete, documents_bucket(), file_path)
