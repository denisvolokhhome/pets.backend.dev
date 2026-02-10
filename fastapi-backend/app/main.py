"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
import time

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy.exc import NoResultFound
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.routers import auth, pets, breeds, breedings, locations, users, geocoding, search

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests and responses."""
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response details."""
        # Generate request ID for tracing
        request_id = id(request)
        
        # Extract user ID if available (from auth token)
        user_id = None
        try:
            # Try to get user from request state (set by auth dependency)
            if hasattr(request.state, "user"):
                user_id = str(request.state.user.id)
        except Exception:
            pass
        
        # Log request
        start_time = time.time()
        logger.info(
            f"Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "user_id": user_id,
                "client": request.client.host if request.client else None
            }
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            logger.info(
                f"Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2)
                }
            )
            
            return response
            
        except Exception as exc:
            # Calculate duration
            duration = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "user_id": user_id,
                    "duration_ms": round(duration * 1000, 2),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)
                }
            )
            
            # Re-raise to let exception handlers deal with it
            raise


# Create settings instance for the application
settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup: Create storage directory if it doesn't exist
    storage_path = Path(settings.storage_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    
    print(f"✓ Storage directory created/verified at: {storage_path.absolute()}")
    print(f"✓ Application started: {settings.app_name}")
    print(f"✓ Debug mode: {settings.debug}")
    
    yield
    
    # Shutdown
    print(f"✓ Application shutdown: {settings.app_name}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
    Pet Breeding Management System API
    
    This API provides comprehensive management for pet breeding operations including:
    
    * **Authentication**: User registration, login, and JWT-based authentication
    * **User Profiles**: Manage breedery information, profile images, and search tags
    * **Pets**: Complete CRUD operations for pet records with image upload support
    * **Breeds**: Management of dog breed information
    * **Litters**: Tracking of puppy breedings
    * **Locations**: Management of breeder locations
    
    ## Authentication
    
    Most endpoints require authentication using JWT tokens. To authenticate:
    
    1. Register a new user at `/api/auth/register`
    2. Login at `/api/auth/jwt/login` to receive a JWT token
    3. Include the token in the `Authorization` header as `Bearer <token>`
    
    ## API Contract
    
    This API maintains compatibility with the Laravel implementation, ensuring:
    - Same URL structure with `/api/` prefix
    - Consistent JSON request/response formats
    - UUID primary keys for main entities
    - Soft deletion for pets (is_deleted flag)
    
    ## Features
    
    - **UUID Primary Keys**: All main entities use UUID v4 for primary keys
    - **Async Operations**: All database operations use async/await patterns
    - **Image Processing**: Automatic image optimization and resizing
    - **Soft Deletion**: Pets are soft-deleted (is_deleted flag) for data preservation
    - **Health Records**: Comprehensive tracking of pet health information
    - **Referential Integrity**: Foreign key constraints ensure data consistency
    - **User Isolation**: Users can only access their own locations and pets
    
    ## Error Handling
    
    All errors return consistent JSON responses with:
    - `detail`: Human-readable error message
    - `error_code`: Machine-readable error code
    
    Common HTTP status codes:
    - `200`: Success
    - `201`: Created
    - `204`: No Content (successful deletion)
    - `401`: Unauthorized (authentication required)
    - `403`: Forbidden (not authorized)
    - `404`: Not Found
    - `422`: Validation Error
    - `500`: Internal Server Error
    
    ## Additional Documentation
    
    For detailed API usage examples, see the [API Documentation](API_DOCUMENTATION.md) file.
    
    ## Rate Limiting
    
    Currently no rate limiting is enforced, but may be added in future versions.
    """,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://example.com/license",
    },
    openapi_tags=[
        {
            "name": "auth",
            "description": "Authentication operations including registration, login, and password management.",
        },
        {
            "name": "users",
            "description": "User profile management. Update profile information, manage breedery details, and upload profile images.",
        },
        {
            "name": "pets",
            "description": "Pet management operations. Create, read, update, and delete pet records. Upload pet images and manage health records.",
        },
        {
            "name": "breeds",
            "description": "Dog breed management. Manage breed information and classifications.",
        },
        {
            "name": "breedings",
            "description": "Breeding management. Track puppy breedings and associate pets with breedings.",
        },
        {
            "name": "locations",
            "description": "Location management. Manage breeder locations and facilities.",
        },
        {
            "name": "geocoding",
            "description": "Geocoding operations. Convert between ZIP codes and coordinates.",
        },
        {
            "name": "search",
            "description": "Location-based search operations. Find breeders and pets near a geographic location.",
        },
    ],
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)


# Mount static files for image serving
# Ensure storage directory exists before mounting
storage_path = Path(settings.storage_path)
storage_path.mkdir(parents=True, exist_ok=True)

app.mount(
    settings.storage_url,
    StaticFiles(directory=str(storage_path)),
    name="storage"
)


@app.get("/")
async def root() -> dict:
    """Root endpoint returning API information."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "operational",
        "docs": "/api/docs"
    }


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, tags=["users"])
app.include_router(pets.router, tags=["pets"])
app.include_router(breeds.router, tags=["breeds"])
app.include_router(breedings.router, tags=["breedings"])
app.include_router(locations.router, tags=["locations"])
app.include_router(geocoding.router, tags=["geocoding"])
app.include_router(search.router, tags=["search"])


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app_name": settings.app_name
    }


# Global exception handlers

@app.exception_handler(NoResultFound)
async def not_found_handler(request: Request, exc: NoResultFound) -> JSONResponse:
    """Handle SQLAlchemy NoResultFound exceptions."""
    logger.warning(f"Resource not found: {request.url.path}")
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Resource not found",
            "error_code": "NOT_FOUND"
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions including authorization errors."""
    # Log based on status code
    if exc.status_code == 403:
        logger.warning(
            f"Authorization failure: {request.url.path} - User attempted to access forbidden resource"
        )
    elif exc.status_code >= 500:
        logger.error(f"HTTP error {exc.status_code}: {request.url.path} - {exc.detail}")
    else:
        logger.info(f"HTTP {exc.status_code}: {request.url.path}")
    
    # Map status codes to error codes
    error_code_map = {
        404: "NOT_FOUND",
        403: "FORBIDDEN",
        401: "UNAUTHORIZED",
        422: "VALIDATION_ERROR",
        400: "BAD_REQUEST",
    }
    
    error_code = error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": error_code
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    # Log the full exception with stack trace
    logger.error(
        f"Unhandled exception: {request.url.path}",
        exc_info=True,
        extra={
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None
        }
    )
    
    if settings.debug:
        # In debug mode, return detailed error information
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            }
        )
    else:
        # In production, return generic error message
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_code": "INTERNAL_ERROR"
            }
        )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
