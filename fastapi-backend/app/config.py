"""Application configuration using Pydantic Settings."""

import os
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL database URL with asyncpg driver"
    )

    # Authentication Configuration
    secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT token generation"
    )
    jwt_lifetime_seconds: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="JWT token lifetime in seconds (5 min to 24 hours)"
    )

    # Storage Configuration
    storage_path: str = Field(
        default="storage/app",
        description="Path to storage directory for uploaded files"
    )
    storage_url: str = Field(
        default="/storage",
        description="URL prefix for serving static files"
    )

    # Application Configuration
    app_name: str = Field(
        default="Pet Breeding API",
        description="Application name"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    allowed_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins"
    )

    # Server Configuration
    host: str = Field(
        default="0.0.0.0",
        description="Server host"
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Server port"
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching"
    )

    # Geocoding Configuration
    nominatim_url: str = Field(
        default="https://nominatim.openstreetmap.org",
        description="Nominatim geocoding service URL"
    )
    geocoding_user_agent: str = Field(
        default="BreedyPetSearch/1.0",
        description="User agent for geocoding requests"
    )
    geocoding_rate_limit: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Geocoding rate limit (requests per second)"
    )
    geocoding_cache_ttl: int = Field(
        default=86400,
        ge=3600,
        le=604800,
        description="Geocoding cache TTL in seconds (1 hour to 7 days)"
    )

    # Image Upload Configuration
    max_image_size_mb: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum image size in megabytes"
    )
    allowed_image_types: str = Field(
        default="image/jpeg,image/png,image/webp",
        description="Comma-separated list of allowed image MIME types"
    )
    image_max_width: int = Field(
        default=1920,
        ge=100,
        le=4096,
        description="Maximum image width in pixels"
    )
    image_max_height: int = Field(
        default=1920,
        ge=100,
        le=4096,
        description="Maximum image height in pixels"
    )
    image_quality: int = Field(
        default=85,
        ge=1,
        le=100,
        description="Image compression quality (1-100)"
    )

    # Google OAuth Configuration
    google_oauth_client_id: str = Field(
        default="",
        description="Google OAuth 2.0 client ID"
    )
    google_oauth_client_secret: str = Field(
        default="",
        description="Google OAuth 2.0 client secret"
    )
    google_oauth_redirect_uri: str = Field(
        default="http://breedly.com:8000/api/auth/google/callback",
        description="Google OAuth redirect URI"
    )
    frontend_url: str = Field(
        default="http://breedly.com:4200",
        description="Frontend URL for OAuth redirects"
    )

    model_config = SettingsConfigDict(
        env_file=".env" if not os.getenv("TESTING") else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate that database URL uses asyncpg driver."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use asyncpg driver (postgresql+asyncpg://)"
            )
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate that secret key is sufficiently long."""
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security"
            )
        return v

    def get_allowed_origins_list(self) -> List[str]:
        """Parse allowed origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    def get_allowed_image_types_list(self) -> List[str]:
        """Parse allowed image types from comma-separated string."""
        return [mime_type.strip() for mime_type in self.allowed_image_types.split(",")]

    @property
    def max_image_size_bytes(self) -> int:
        """Get maximum image size in bytes."""
        return self.max_image_size_mb * 1024 * 1024
