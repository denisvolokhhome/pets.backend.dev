"""Authentication routes using fastapi-users."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import auth_backend, fastapi_users, get_user_manager
from app.schemas.user import UserRead, UserCreate, UserUpdate, PetSeekerCreate, GuestToAccountCreate, ServiceProviderCreate
from app.services.user_manager import UserManager
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationCreate
from app.middleware.rate_limiter import rate_limiter, get_client_ip
from app.dependencies import current_active_user
from app.models.user import User


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

# NOTE: We do NOT include the default fastapi-users register router.
# Instead we define a custom /register endpoint below that checks for
# SSO-created accounts and returns a specific error code so the frontend
# can redirect the user to the sign-in page.
# router.include_router(
#     fastapi_users.get_register_router(UserRead, UserCreate),
#     tags=["auth"],
# )

# Include reset password router
router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)

# NOTE: We do NOT include the default fastapi-users verify router.
# Instead we define custom /verify and /request-verify-token endpoints
# below with rate limiting to prevent SMTP abuse.
# router.include_router(
#     fastapi_users.get_verify_router(UserRead),
#     tags=["auth"],
# )

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
    code: Optional[str] = None,
    error: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Handle Google OAuth callback and create/authenticate user.
    
    Args:
        code: Authorization code from Google
        error: Error code from Google (e.g. access_denied)
        session: Database session
        user_manager: User manager for user operations
        
    Returns:
        dict: Contains access_token and user data
        
    Raises:
        HTTPException: If OAuth flow fails or user creation fails
    """
    from fastapi.responses import RedirectResponse

    # Handle Google OAuth errors (user denied consent, etc.)
    if error or not code:
        error_url = f"{settings.frontend_url}/login?error={error or 'oauth_failed'}"
        return RedirectResponse(url=error_url)
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
        
        # Log token for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Got access token: {token.get('access_token', 'N/A')[:20]}...")
        
        # Get user info from Google using userinfo endpoint directly
        # The httpx_oauth get_id_email method may have issues, so we'll call the API directly
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token['access_token']}"}
                )
                response.raise_for_status()
                user_data = response.json()
                
            logger.info(f"Got user data: {user_data}")
            
            email = user_data.get("email")
            oauth_id = user_data.get("id")
            
            if not email or not oauth_id:
                raise ValueError(f"Missing email or id in user data: {user_data}")
                
        except Exception as user_info_error:
            logger.error(f"Failed to get user info: {str(user_info_error)}")
            logger.error(f"Token keys: {token.keys()}")
            raise
        
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
        
        # Redirect to frontend with token
        frontend_redirect_url = f"{settings.frontend_url}/auth/callback?token={token_str}"
        return RedirectResponse(url=frontend_redirect_url)
        
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"OAuth callback error: {str(e)}")
        
        # Redirect to frontend with error
        error_url = f"{settings.frontend_url}/login?error=oauth_failed"
        return RedirectResponse(url=error_url)


@router.post("/register", tags=["auth"], status_code=status.HTTP_201_CREATED)
async def register_breeder(
    user_data: UserCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Register a new breeder account.

    Replaces the default fastapi-users register endpoint so we can
    detect SSO-created accounts and return a specific error code.
    """
    from app.models.user import User
    from sqlalchemy import select
    from app.middleware.rate_limiter import hash_ip
    import logging

    logger = logging.getLogger(__name__)

    # Rate limiting — 3 registrations per IP per 10 minutes
    client_ip = await get_client_ip(request)
    hashed = hash_ip(client_ip)
    await rate_limiter.check_rate_limit(
        key=f"register:{hashed}",
        max_requests=3,
        window_seconds=600,
    )

    # Check for existing user with SSO-specific error
    stmt = select(User).where(User.email == user_data.email)
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.oauth_provider:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="REGISTER_SSO_ACCOUNT_EXISTS",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS",
        )

    try:
        user = await user_manager.create(user_data, request=request)
    except Exception as e:
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )

    return UserRead.model_validate(user, from_attributes=True)


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
    from app.middleware.rate_limiter import hash_ip
    import logging
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    
    logger = logging.getLogger(__name__)
    
    # Rate limiting: 3 registration attempts per IP per 10 minutes
    client_ip = await get_client_ip(request)
    hashed = hash_ip(client_ip)
    await rate_limiter.check_rate_limit(
        key=f"register:{hashed}",
        max_requests=3,
        window_seconds=600
    )
    
    try:
        # Check if user already exists
        stmt = select(User).where(User.email == pet_seeker_data.email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.warning(f"Attempt to register existing email: {pet_seeker_data.email}")
            # If the existing account was created via SSO, return a specific error
            if existing_user.oauth_provider:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="REGISTER_SSO_ACCOUNT_EXISTS"
                )
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
    from app.middleware.rate_limiter import hash_ip
    import logging
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    
    logger = logging.getLogger(__name__)
    
    # Rate limiting: 3 registration attempts per IP per 10 minutes
    client_ip = await get_client_ip(request)
    hashed = hash_ip(client_ip)
    await rate_limiter.check_rate_limit(
        key=f"register:{hashed}",
        max_requests=3,
        window_seconds=600
    )
    
    try:
        # Check if user already exists
        stmt = select(User).where(User.email == guest_data.email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.warning(f"Attempt to register existing email: {guest_data.email}")
            if existing_user.oauth_provider:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="REGISTER_SSO_ACCOUNT_EXISTS"
                )
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


@router.post("/request-verify-token", tags=["auth"])
async def request_verify_token(
    request: Request,
    email_body: dict,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Request a new email verification token.

    Rate limited: 2 requests per email per 5 minutes, 5 per IP per 10 minutes.
    """
    import logging
    from sqlalchemy import select
    from pydantic import EmailStr

    logger = logging.getLogger(__name__)
    email = email_body.get("email", "")

    if not email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is required")

    # Rate limit by IP
    client_ip = await get_client_ip(request)
    await rate_limiter.check_rate_limit(
        key=f"verify_ip:{client_ip}",
        max_requests=5,
        window_seconds=600,
    )

    # Rate limit by email (stricter)
    await rate_limiter.check_rate_limit(
        key=f"verify_email:{email}",
        max_requests=2,
        window_seconds=300,
    )

    # Find user
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user and not user.is_verified:
        try:
            await user_manager.request_verify(user)
        except Exception as e:
            logger.warning(f"Failed to send verification for {email}: {e}")

    # Always return 202 to prevent email enumeration
    return {"detail": "If the email exists and is not verified, a verification link has been sent."}


@router.post("/verify", tags=["auth"])
async def verify_user(
    request: Request,
    token_body: dict,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Verify a user's email using the token from the verification email."""
    from fastapi_users.exceptions import InvalidVerifyToken, UserAlreadyVerified

    token = token_body.get("token", "")
    if not token:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Token is required")

    # Rate limit by IP
    client_ip = await get_client_ip(request)
    await rate_limiter.check_rate_limit(
        key=f"verify_token:{client_ip}",
        max_requests=10,
        window_seconds=300,
    )

    try:
        from app.dependencies import get_jwt_strategy
        user = await user_manager.verify(token, request)
        # Issue a JWT so the frontend can auto-login after verification
        strategy = get_jwt_strategy()
        access_token = await strategy.write_token(user)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserRead.model_validate(user, from_attributes=True),
        }
    except InvalidVerifyToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="VERIFY_USER_BAD_TOKEN")
    except UserAlreadyVerified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="VERIFY_USER_ALREADY_VERIFIED")


@router.post("/register/service-provider", tags=["auth"], status_code=status.HTTP_201_CREATED)
async def register_service_provider(
    service_provider_data: ServiceProviderCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Register a new service provider account.

    Creates a user with account_type='service', is_breeder=False, and associates
    the user with the provided service categories.

    Args:
        service_provider_data: Service provider registration data including
            email, password, optional name, and at least one category_id
        request: Request object for rate limiting
        session: Database session
        user_manager: User manager for user operations

    Returns:
        UserRead: The created user data

    Raises:
        HTTPException 400: If email is already registered
        HTTPException 422: If category_ids is empty or contains invalid/inactive category IDs
        HTTPException 429: If rate limit exceeded
    """
    from app.models.user import User
    from app.models.service_category import ServiceCategory, user_service_categories
    from app.middleware.rate_limiter import hash_ip
    from sqlalchemy import select, insert
    from sqlalchemy.exc import IntegrityError
    import logging

    logger = logging.getLogger(__name__)

    # Rate limiting: 3 registration attempts per IP per 10 minutes
    client_ip = await get_client_ip(request)
    hashed = hash_ip(client_ip)
    await rate_limiter.check_rate_limit(
        key=f"register:{hashed}",
        max_requests=3,
        window_seconds=600,
    )

    # Explicit check: at least one category_id required
    # (Pydantic min_length=1 already enforces this, but we add an explicit guard for clarity)
    if not service_provider_data.category_ids or len(service_provider_data.category_ids) < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one category_id is required for service provider registration",
        )

    # Check for duplicate email
    stmt = select(User).where(User.email == service_provider_data.email)
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.oauth_provider:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="REGISTER_SSO_ACCOUNT_EXISTS",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS",
        )

    # Validate all category_ids exist and are active
    category_ids = service_provider_data.category_ids
    cat_stmt = select(ServiceCategory).where(
        ServiceCategory.id.in_(category_ids),
        ServiceCategory.is_active == True,
    )
    cat_result = await session.execute(cat_stmt)
    valid_categories = cat_result.scalars().all()
    valid_category_ids = {cat.id for cat in valid_categories}

    invalid_ids = [cid for cid in category_ids if cid not in valid_category_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid or inactive category_id(s): {invalid_ids}",
        )

    try:
        # Create user via user_manager (handles password hashing and on_after_register hooks)
        user_create = UserCreate(
            email=service_provider_data.email,
            password=service_provider_data.password,
            is_breeder=False,  # Service providers are not breeders
        )
        user = await user_manager.create(user_create, request=request)

        # Update account_type and name — user_manager.create sets is_breeder=False
        # but we need to explicitly set account_type='service'
        user.account_type = "service"
        user.is_breeder = False
        if service_provider_data.name:
            user.name = service_provider_data.name

        await session.commit()
        await session.refresh(user)

        # Insert user_service_categories associations
        for category_id in category_ids:
            await session.execute(
                insert(user_service_categories).values(
                    user_id=user.id,
                    category_id=category_id,
                )
            )

        await session.commit()
        await session.refresh(user)

        logger.info(
            f"Service provider registered: user_id={user.id}, "
            f"email={user.email}, categories={category_ids}"
        )

        return UserRead.model_validate(user, from_attributes=True)

    except HTTPException:
        raise
    except IntegrityError as e:
        logger.error(f"Service provider registration integrity error: {str(e)}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS",
        )
    except Exception as e:
        logger.error(f"Service provider registration error: {str(e)}")
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str or "unique constraint" in error_str:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGISTER_USER_ALREADY_EXISTS",
            )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )


@router.post("/convert-to-breeder", tags=["auth"])
async def convert_to_breeder(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Convert a pet seeker account to a breeder account.

    This is a one-way, irreversible operation. Once converted, the user
    cannot revert to pet seeker without contacting support@breedly.us.

    As a breeder the user will not be able to message other breeders
    within the application. The breeder account must be verified before
    the user can publish offspring listings or their public profile.

    Returns:
        dict: Updated user data and confirmation message
    """
    import logging

    logger = logging.getLogger(__name__)

    if user.is_breeder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ALREADY_BREEDER",
        )

    # Flip the flag
    user.is_breeder = True
    await session.commit()
    await session.refresh(user)

    # Send notification about the conversion
    try:
        notification_service = NotificationService()
        await notification_service.create_notification(
            db=session,
            notification_data=NotificationCreate(
                user_id=user.id,
                type="account_type_changed",
                title="Account converted to Breeder",
                message=(
                    "Your account has been converted to a Breeder account. "
                    "Please note: as a breeder you cannot message other breeders "
                    "within the application, and this change is irreversible. "
                    "To revert, contact support@breedly.us. "
                    "You will need to verify your breeding account before you can "
                    "publish offspring listings or your public breeder profile."
                ),
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to create conversion notification for user {user.id}: {e}")

    logger.info(f"User {user.id} converted from pet seeker to breeder")

    return {
        "message": "Account successfully converted to breeder",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "is_breeder": user.is_breeder,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "name": user.name,
        },
    }
