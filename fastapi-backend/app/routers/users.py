"""User profile management routes."""
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate, ProfileImageResponse
from app.services.file_service import FileService


# Initialize router
router = APIRouter(prefix="/api/users", tags=["users"])

# Initialize settings
settings = Settings()


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(
    user: User = Depends(current_active_user),
) -> User:
    """
    Get current user's profile information.
    
    Returns:
        User: Current authenticated user's profile data
    """
    return user


@router.patch("/me", response_model=UserRead)
async def update_current_user_profile(
    user_update: UserUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """
    Update current user's profile information.
    
    Args:
        user_update: User update data (breedery_name, breedery_description, search_tags)
        user: Current authenticated user
        session: Database session
        
    Returns:
        User: Updated user profile data
    """
    # Update only provided fields
    update_data = user_update.model_dump(exclude_unset=True, exclude={"password", "email"})
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    # Commit changes
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    return user


@router.post("/me/profile-image", response_model=ProfileImageResponse)
async def upload_profile_image(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Upload and set user profile image.
    
    Args:
        file: Uploaded image file (JPEG, PNG, GIF, WebP, max 5MB)
        user: Current authenticated user
        session: Database session
        
    Returns:
        ProfileImageResponse: Image path and success message
        
    Raises:
        HTTPException: If file validation fails or storage error occurs
    """
    # Initialize file service
    file_service = FileService(settings)
    
    try:
        # Delete old profile image if exists
        if user.profile_image_path:
            try:
                await file_service.delete_profile_image(user.profile_image_path)
            except FileNotFoundError:
                # Old image doesn't exist, continue
                pass
        
        # Save new profile image
        image_path = await file_service.save_profile_image(file, user.id)
        
        # Update user profile
        user.profile_image_path = image_path
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        return {
            "profile_image_path": image_path,
            "message": "Profile image uploaded successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload profile image: {str(e)}"
        )


@router.get("/me/profile-image")
async def get_profile_image(
    user: User = Depends(current_active_user),
) -> FileResponse:
    """
    Serve user's profile image.
    
    Args:
        user: Current authenticated user
        
    Returns:
        FileResponse: Profile image file
        
    Raises:
        HTTPException: If user has no profile image or file not found
    """
    if not user.profile_image_path:
        raise HTTPException(
            status_code=404,
            detail="User has no profile image"
        )
    
    # Construct full file path
    storage_path = Path(settings.storage_path).parent
    file_path = storage_path / user.profile_image_path
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Profile image file not found"
        )
    
    return FileResponse(
        path=str(file_path),
        media_type="image/jpeg",
        filename=file_path.name
    )
