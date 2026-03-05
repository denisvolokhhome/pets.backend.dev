"""Offspring image service for managing multiple images per offspring."""
from typing import List, Optional
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, UploadFile

from app.models.offspring_image import OffspringImage
from app.models.offspring import Offspring
from app.services.file_service import FileService


class OffspringImageService:
    """Service for managing offspring images with primary designation and ordering."""
    
    def __init__(self, file_service: FileService):
        """
        Initialize OffspringImageService.
        
        Args:
            file_service: FileService instance for image storage
        """
        self.file_service = file_service
    
    async def upload_image(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        file: UploadFile,
        user_id: uuid.UUID,
        is_primary: bool = False
    ) -> OffspringImage:
        """
        Upload and save an image for an offspring.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            file: Uploaded image file
            user_id: ID of the authenticated breeder
            is_primary: Whether to set as primary image
            
        Returns:
            Created OffspringImage instance
            
        Raises:
            HTTPException: If offspring not found, access denied, or upload fails
        """
        # Verify offspring exists and belongs to user
        offspring_query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.user_id == user_id
        )
        result = await db.execute(offspring_query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or access denied"
            )
        
        # Upload image using file service
        try:
            image_path, _ = await self.file_service.save_image(file, offspring_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        # Get current max display_order
        max_order_query = select(OffspringImage.display_order).where(
            OffspringImage.offspring_id == offspring_id
        ).order_by(OffspringImage.display_order.desc()).limit(1)
        max_order_result = await db.execute(max_order_query)
        max_order = max_order_result.scalar_one_or_none()
        display_order = (max_order + 1) if max_order is not None else 0
        
        # If setting as primary, unset other primary images
        if is_primary:
            await self._unset_primary_images(db, offspring_id)
        
        # Create image record
        offspring_image = OffspringImage(
            offspring_id=offspring_id,
            image_path=image_path,
            is_primary=is_primary,
            display_order=display_order
        )
        
        db.add(offspring_image)
        await db.commit()
        await db.refresh(offspring_image)
        
        return offspring_image
    
    async def delete_image(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        image_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> None:
        """
        Delete an offspring image.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            image_id: ID of the image to delete
            user_id: ID of the authenticated breeder
            
        Raises:
            HTTPException: If image not found or access denied
        """
        # Verify offspring belongs to user and get image
        offspring_query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.user_id == user_id
        )
        result = await db.execute(offspring_query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or access denied"
            )
        
        # Get image
        image_query = select(OffspringImage).where(
            OffspringImage.id == image_id,
            OffspringImage.offspring_id == offspring_id
        )
        image_result = await db.execute(image_query)
        image = image_result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found"
            )
        
        # Delete file from storage
        try:
            await self.file_service.delete_image(image.image_path)
        except FileNotFoundError:
            # File already deleted, continue with database cleanup
            pass
        
        # Delete database record
        await db.delete(image)
        await db.commit()
    
    async def set_primary_image(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        image_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> OffspringImage:
        """
        Set an image as the primary image for an offspring.
        
        Ensures only one image per offspring is marked as primary.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            image_id: ID of the image to set as primary
            user_id: ID of the authenticated breeder
            
        Returns:
            Updated OffspringImage instance
            
        Raises:
            HTTPException: If image not found or access denied
        """
        # Verify offspring belongs to user
        offspring_query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.user_id == user_id
        )
        result = await db.execute(offspring_query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or access denied"
            )
        
        # Get image
        image_query = select(OffspringImage).where(
            OffspringImage.id == image_id,
            OffspringImage.offspring_id == offspring_id
        )
        image_result = await db.execute(image_query)
        image = image_result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found"
            )
        
        # Unset other primary images
        await self._unset_primary_images(db, offspring_id)
        
        # Set this image as primary
        image.is_primary = True
        await db.commit()
        await db.refresh(image)
        
        return image
    
    async def reorder_images(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        image_ids: List[uuid.UUID],
        user_id: uuid.UUID
    ) -> List[OffspringImage]:
        """
        Reorder images for an offspring.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            image_ids: List of image IDs in desired order
            user_id: ID of the authenticated breeder
            
        Returns:
            List of updated OffspringImage instances
            
        Raises:
            HTTPException: If offspring not found or access denied
        """
        # Verify offspring belongs to user
        offspring_query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.user_id == user_id
        )
        result = await db.execute(offspring_query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or access denied"
            )
        
        # Get all images for this offspring
        images_query = select(OffspringImage).where(
            OffspringImage.offspring_id == offspring_id
        )
        images_result = await db.execute(images_query)
        images = {img.id: img for img in images_result.scalars().all()}
        
        # Validate all image IDs belong to this offspring
        if set(image_ids) != set(images.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image IDs do not match offspring images"
            )
        
        # Update display_order for each image
        updated_images = []
        for order, image_id in enumerate(image_ids):
            image = images[image_id]
            image.display_order = order
            updated_images.append(image)
        
        await db.commit()
        
        # Refresh all images
        for image in updated_images:
            await db.refresh(image)
        
        return updated_images
    
    async def _unset_primary_images(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID
    ) -> None:
        """
        Unset all primary images for an offspring.
        
        Internal helper method to ensure only one primary image.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
        """
        stmt = (
            update(OffspringImage)
            .where(
                OffspringImage.offspring_id == offspring_id,
                OffspringImage.is_primary == True
            )
            .values(is_primary=False)
        )
        await db.execute(stmt)
    
    async def get_images(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID
    ) -> List[OffspringImage]:
        """
        Get all images for an offspring ordered by display_order.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            
        Returns:
            List of OffspringImage instances
        """
        query = select(OffspringImage).where(
            OffspringImage.offspring_id == offspring_id
        ).order_by(OffspringImage.display_order)
        
        result = await db.execute(query)
        images = result.scalars().all()
        
        return list(images)
