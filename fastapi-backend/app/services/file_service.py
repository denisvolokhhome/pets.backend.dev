"""File service for handling image uploads and storage."""

import io
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import UploadFile
from PIL import Image

from app.config import Settings


class FileService:
    """Service for handling file uploads, particularly pet images."""

    def __init__(self, settings: Settings):
        """
        Initialize FileService with configuration.

        Args:
            settings: Application settings containing storage configuration
        """
        self.settings = settings
        self.storage_path = Path(settings.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
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

        # Generate unique filename
        ext = Path(file.filename).suffix if file.filename else ".jpg"
        if not ext:
            ext = ".jpg"
        filename = f"{pet_id}_{uuid.uuid4()}{ext}"
        file_path = self.storage_path / filename

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
        image.save(file_path, optimize=True, quality=self.quality)

        # Return relative path and original filename
        relative_path = str(file_path.relative_to(self.storage_path.parent))
        original_filename = file.filename or filename

        return relative_path, original_filename

    async def delete_image(self, image_path: str) -> None:
        """
        Delete image file from storage.

        Args:
            image_path: Relative path to the image file

        Raises:
            FileNotFoundError: If image file does not exist
        """
        file_path = self.storage_path.parent / image_path
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        file_path.unlink()

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
