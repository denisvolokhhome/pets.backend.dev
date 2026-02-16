"""Authentication routes using fastapi-users."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import auth_backend, fastapi_users, get_user_manager
from app.schemas.user import UserRead, UserCreate, UserUpdate, PetSeekerCreate, GuestToAccountCreate
from app.services.user_manager import UserManager
from app.middleware.rate_limiter import rate_limiter, get_client_ip


# Initialize settings
settings = Settings()

# Initialize Google OAuth client
google_oauth_client = GoogleOAuth2(
    client_id=settings.google_oauth_client_id,
    client_secret=settings.google_oauth_client_secret,
)


# Create router for authentication endpoints
router = APIRouter()

# Include auth router for JWT login/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)

# Include register router
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"],
)

# Include reset password router
router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)

# Include verify router
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    tags=["auth"],
)

# Include users router (for /users/me endpoint)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


# Google OAuth endpoints
@router.get("/google/authorize", tags=["auth"])
async def google_authorize():
    """
    Initiate Google OAuth flow by generating authorization URL.
    
    Returns:
        dict: Contains authorization_url for redirecting user to Google consent screen
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    
    authorization_url = await google_oauth_client.get_authorization_url(
        redirect_uri=settings.google_oauth_redirect_uri,
        scope=["openid", "email", "profile"]
    )
    
    return {"authorization_url": authorization_url}


@router.get("/google/callback", tags=["auth"])
async def google_callback(
    code: str,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Handle Google OAuth callback and create/authenticate user.
    
    Args:
        code: Authorization code from Google
        session: Database session
        user_manager: User manager for user operations
        
    Returns:
        dict: Contains access_token and user data
        
    Raises:
        HTTPException: If OAuth flow fails or user creation fails
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    
    try:
        # Exchange authorization code for access token
        token = await google_oauth_client.get_access_token(
            code,
            redirect_uri=settings.google_oauth_redirect_uri
        )
        
        # Get user info from Google
        user_info = await google_oauth_client.get_id_email(token["access_token"])
        email = user_info[1]  # email is second element in tuple
        oauth_id = user_info[0]  # id is first element
        
        # Try to get existing user by email or oauth_id
        from sqlalchemy import select, or_
        from app.models.user import User
        
        stmt = select(User).where(
            or_(
                User.email == email,
                (User.oauth_provider == "google") & (User.oauth_id == oauth_id)
            )
        )
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            # Update OAuth info if not set
            if not existing_user.oauth_provider:
                existing_user.oauth_provider = "google"
                existing_user.oauth_id = oauth_id
                await session.commit()
                await session.refresh(existing_user)
            user = existing_user
        else:
            # Create new pet seeker user
            from app.schemas.user import UserCreate
            import secrets
            
            # Generate a random password for OAuth users (they won't use it)
            random_password = secrets.token_urlsafe(32)
            
            user_create = UserCreate(
                email=email,
                password=random_password,
                is_breeder=False,  # OAuth users are pet seekers
                is_verified=True,  # Google verified the email
            )
            
            # Create user through user manager
            user = await user_manager.create(user_create)
            
            # Set OAuth fields
            user.oauth_provider = "google"
            user.oauth_id = oauth_id
            await session.commit()
            await session.refresh(user)
        
        # Generate JWT token using the auth backend
        from app.dependencies import get_jwt_strategy
        strategy = get_jwt_strategy()
        token_str = await strategy.write_token(user)
        
        # Return token and user data
        return {
            "access_token": token_str,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "is_breeder": user.is_breeder,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
            }
        }
        
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"OAuth callback error: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authentication failed: {str(e)}"
        )


@router.post("/register/pet-seeker", tags=["auth"])
async def register_pet_seeker(
    pet_seeker_data: PetSeekerCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Register a new pet seeker account.
    
    Rate limited to prevent abuse and email enumeration attacks.
    
    Args:
        pet_seeker_data: Pet seeker registration data (email, password, optional name)
        request: Request object for rate limiting
        session: Database session
        user_manager: User manager for user operations
        
    Returns:
        dict: Contains access_token and user data
        
    Raises:
        HTTPException: If registration fails or rate limit exceeded
    """
    from app.schemas.user import UserCreate
    from app.dependencies import get_jwt_strategy
    from app.services.message_linking_service import MessageLinkingService
    from app.models.user import User
    import logging
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    
    logger = logging.getLogger(__name__)
    
    # Rate limiting: 5 registration attempts per IP per 5 minutes
    client_ip = await get_client_ip(request)
    await rate_limiter.check_rate_limit(
        key=f"register:{client_ip}",
        max_requests=5,
        window_seconds=300
    )
    
    try:
        # Check if user already exists
        stmt = select(User).where(User.email == pet_seeker_data.email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.warning(f"Attempt to register existing email: {pet_seeker_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS"
            )
        
        # Create UserCreate schema with is_breeder=False
        user_create = UserCreate(
            email=pet_seeker_data.email,
            password=pet_seeker_data.password,
            is_breeder=False,  # Pet seekers are not breeders
        )
        
        # Create user through user manager (handles password hashing)
        user = await user_manager.create(user_create)
        
        # Set name if provided
        if pet_seeker_data.name:
            user.name = pet_seeker_data.name
            await session.commit()
            await session.refresh(user)
        
        # Link any existing guest messages to this account
        linking_service = MessageLinkingService()
        linking_result = await linking_service.link_messages_to_account(
            email=pet_seeker_data.email,
            user_id=user.id,
            session=session
        )
        
        # Log linking results
        logger.info(
            f"Pet seeker registration: linked {linking_result['linked_count']} "
            f"messages for {pet_seeker_data.email}"
        )
        
        # Generate JWT token
        strategy = get_jwt_strategy()
        token_str = await strategy.write_token(user)
        
        # Return token and user data with linked message count
        return {
            "access_token": token_str,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "is_breeder": user.is_breeder,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "name": user.name,
            },
            "linked_messages_count": linking_result["linked_count"]
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like the user already exists check)
        raise
    except IntegrityError as e:
        # Database constraint violation (duplicate email)
        logger.error(f"Pet seeker registration integrity error: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS"
        )
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Pet seeker registration error: {str(e)}")
        
        # Check if it's a duplicate email error
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str or "unique constraint" in error_str:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS"
            )
        
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/register/from-message", tags=["auth"])
async def register_from_message(
    guest_data: GuestToAccountCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Convert a guest message sender to a registered pet seeker account.
    
    Rate limited to prevent abuse and email enumeration attacks.
    
    This endpoint creates a pet seeker account and links any existing messages
    sent from the provided email address to the new account.
    
    Args:
        guest_data: Guest account data (pre-filled email, password, optional name)
        request: Request object for rate limiting
        session: Database session
        user_manager: User manager for user operations
        
    Returns:
        dict: Contains access_token, user data, and count of linked messages
        
    Raises:
        HTTPException: If registration fails or rate limit exceeded
    """
    from app.schemas.user import UserCreate
    from app.dependencies import get_jwt_strategy
    from app.services.message_linking_service import MessageLinkingService
    from app.models.user import User
    import logging
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    
    logger = logging.getLogger(__name__)
    
    # Rate limiting: 5 registration attempts per IP per 5 minutes
    client_ip = await get_client_ip(request)
    await rate_limiter.check_rate_limit(
        key=f"register:{client_ip}",
        max_requests=5,
        window_seconds=300
    )
    
    try:
        # Check if user already exists
        stmt = select(User).where(User.email == guest_data.email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.warning(f"Attempt to register existing email: {guest_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS"
            )
        
        # Create UserCreate schema with is_breeder=False
        user_create = UserCreate(
            email=guest_data.email,
            password=guest_data.password,
            is_breeder=False,  # Guest conversions are pet seekers
        )
        
        # Create user through user manager (handles password hashing)
        user = await user_manager.create(user_create)
        
        # Set name if provided
        if guest_data.name:
            user.name = guest_data.name
            await session.commit()
            await session.refresh(user)
        
        # Link messages to the new account using MessageLinkingService
        linking_service = MessageLinkingService()
        linking_result = await linking_service.link_messages_to_account(
            email=guest_data.email,
            user_id=user.id,
            session=session
        )
        
        # Log linking results
        logger.info(
            f"Guest-to-account conversion: linked {linking_result['linked_count']} "
            f"messages for {guest_data.email}"
        )
        
        # Generate JWT token
        strategy = get_jwt_strategy()
        token_str = await strategy.write_token(user)
        
        # Return token, user data, and linked message count
        return {
            "access_token": token_str,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "is_breeder": user.is_breeder,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "name": user.name,
            },
            "linked_messages_count": linking_result["linked_count"]
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like the user already exists check)
        raise
    except IntegrityError as e:
        # Database constraint violation (duplicate email)
        logger.error(f"Guest-to-account conversion integrity error: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS"
        )
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Guest-to-account conversion error: {str(e)}")
        
        # Check if it's a duplicate email error
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str or "unique constraint" in error_str:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS"
            )
        
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account conversion failed: {str(e)}"
        )
