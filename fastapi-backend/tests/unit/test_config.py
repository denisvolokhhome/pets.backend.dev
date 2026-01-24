"""Unit tests for configuration loading and validation."""

import pytest
import os
from pydantic import ValidationError

from app.config import Settings


class TestConfigurationLoading:
    """Test configuration loading from environment variables."""

    def test_loads_all_required_configuration(self) -> None:
        """Test that configuration loads successfully with all required variables."""
        # Set required environment variables
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32  # 32 character secret key
        
        # Create settings instance
        settings = Settings()
        
        # Verify required fields are loaded
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/testdb"
        assert settings.secret_key == "a" * 32
        assert settings.jwt_lifetime_seconds == 3600  # default value
        assert settings.app_name == "Pet Breeding API"  # default value

    def test_loads_optional_configuration_with_defaults(self) -> None:
        """Test that optional configuration uses default values when not provided."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        # Don't set DEBUG - it should default to False
        if "DEBUG" in os.environ:
            del os.environ["DEBUG"]
        
        settings = Settings()
        
        # Verify default values
        assert settings.storage_path == "storage/app"
        assert settings.storage_url == "/storage"
        assert settings.debug is False
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.max_image_size_mb == 10
        assert settings.image_quality == 85

    def test_loads_custom_configuration_values(self) -> None:
        """Test that custom configuration values override defaults."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "b" * 40
        os.environ["JWT_LIFETIME_SECONDS"] = "7200"
        os.environ["STORAGE_PATH"] = "custom/storage"
        os.environ["DEBUG"] = "true"
        os.environ["PORT"] = "9000"
        os.environ["MAX_IMAGE_SIZE_MB"] = "20"
        
        settings = Settings()
        
        assert settings.secret_key == "b" * 40
        assert settings.jwt_lifetime_seconds == 7200
        assert settings.storage_path == "custom/storage"
        assert settings.debug is True
        assert settings.port == 9000
        assert settings.max_image_size_mb == 20

    def test_missing_database_url_raises_error(self, clean_env) -> None:
        """Test that missing DATABASE_URL raises a clear validation error."""
        os.environ["SECRET_KEY"] = "a" * 32
        # DATABASE_URL is not set
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error mentions the missing field
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("database_url",)
        assert error_dict["type"] == "missing"

    def test_missing_secret_key_raises_error(self, clean_env) -> None:
        """Test that missing SECRET_KEY raises a clear validation error."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        # SECRET_KEY is not set
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error mentions the missing field
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("secret_key",)
        assert error_dict["type"] == "missing"

    def test_invalid_database_url_driver_raises_error(self) -> None:
        """Test that DATABASE_URL without asyncpg driver raises validation error."""
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/testdb"  # Missing +asyncpg
        os.environ["SECRET_KEY"] = "a" * 32
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error message mentions asyncpg requirement
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("database_url",)
        assert "asyncpg" in str(error_dict["msg"]).lower()

    def test_short_secret_key_raises_error(self) -> None:
        """Test that SECRET_KEY shorter than 32 characters raises validation error."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "short"  # Only 5 characters
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error message mentions minimum length
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("secret_key",)
        assert "32 characters" in str(error_dict["msg"])

    def test_invalid_jwt_lifetime_raises_error(self) -> None:
        """Test that invalid JWT_LIFETIME_SECONDS raises validation error."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["JWT_LIFETIME_SECONDS"] = "100"  # Less than minimum 300
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error mentions the constraint
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("jwt_lifetime_seconds",)

    def test_invalid_port_raises_error(self) -> None:
        """Test that invalid PORT value raises validation error."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["PORT"] = "99999"  # Greater than maximum 65535
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify error mentions the port field
        error_dict = exc_info.value.errors()[0]
        assert error_dict["loc"] == ("port",)


class TestConfigurationHelperMethods:
    """Test configuration helper methods."""

    def test_get_allowed_origins_list(self) -> None:
        """Test parsing allowed origins from comma-separated string."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,http://localhost:4200,https://example.com"
        
        settings = Settings()
        origins = settings.get_allowed_origins_list()
        
        assert len(origins) == 3
        assert "http://localhost:3000" in origins
        assert "http://localhost:4200" in origins
        assert "https://example.com" in origins

    def test_get_allowed_image_types_list(self) -> None:
        """Test parsing allowed image types from comma-separated string."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["ALLOWED_IMAGE_TYPES"] = "image/jpeg,image/png,image/webp"
        
        settings = Settings()
        types = settings.get_allowed_image_types_list()
        
        assert len(types) == 3
        assert "image/jpeg" in types
        assert "image/png" in types
        assert "image/webp" in types

    def test_max_image_size_bytes_property(self) -> None:
        """Test conversion of max image size from MB to bytes."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["MAX_IMAGE_SIZE_MB"] = "15"
        
        settings = Settings()
        
        assert settings.max_image_size_bytes == 15 * 1024 * 1024
        assert settings.max_image_size_bytes == 15728640


class TestConfigurationEdgeCases:
    """Test edge cases in configuration."""

    def test_handles_whitespace_in_comma_separated_values(self) -> None:
        """Test that whitespace is trimmed from comma-separated values."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["ALLOWED_ORIGINS"] = " http://localhost:3000 , http://localhost:4200 "
        
        settings = Settings()
        origins = settings.get_allowed_origins_list()
        
        assert origins == ["http://localhost:3000", "http://localhost:4200"]

    def test_case_insensitive_environment_variables(self) -> None:
        """Test that environment variables are case-insensitive."""
        os.environ["database_url"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["secret_key"] = "a" * 32
        
        settings = Settings()
        
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/testdb"
        assert settings.secret_key == "a" * 32

    def test_boolean_string_conversion(self) -> None:
        """Test that boolean strings are correctly converted."""
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/testdb"
        os.environ["SECRET_KEY"] = "a" * 32
        
        # Test various boolean string representations
        os.environ["DEBUG"] = "1"
        settings = Settings()
        assert settings.debug is True
        
        os.environ["DEBUG"] = "true"
        settings = Settings()
        assert settings.debug is True
        
        os.environ["DEBUG"] = "false"
        settings = Settings()
        assert settings.debug is False
        
        os.environ["DEBUG"] = "0"
        settings = Settings()
        assert settings.debug is False
