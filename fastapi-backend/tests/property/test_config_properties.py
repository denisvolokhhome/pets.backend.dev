"""Property-based tests for configuration validation.

Feature: laravel-to-fastapi-migration
"""

import pytest
import os
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from app.config import Settings


# Custom strategies for configuration values
# Use printable ASCII to avoid encoding issues with environment variables
valid_database_url_strategy = st.builds(
    lambda user, password, host, db: f"postgresql+asyncpg://{user}:{password}@{host}/{db}",
    user=st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=ord('a'), max_codepoint=ord('z'))),
    password=st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=ord('a'), max_codepoint=ord('z'))),
    host=st.sampled_from(["localhost", "127.0.0.1", "db.example.com"]),
    db=st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=ord('a'), max_codepoint=ord('z')))
)

invalid_database_url_strategy = st.one_of(
    st.just("postgresql://user:pass@localhost/db"),  # Missing asyncpg
    st.just("mysql://user:pass@localhost/db"),  # Wrong database
    st.just("sqlite:///db.sqlite"),  # Wrong database
    st.just("not-a-url"),  # Invalid format
)

# Use printable ASCII for secret keys to avoid encoding issues
valid_secret_key_strategy = st.text(
    min_size=32,
    max_size=128,
    alphabet=st.characters(min_codepoint=33, max_codepoint=126)  # Printable ASCII
)
invalid_secret_key_strategy = st.text(
    min_size=1,
    max_size=31,
    alphabet=st.characters(min_codepoint=33, max_codepoint=126)  # Printable ASCII
)

valid_jwt_lifetime_strategy = st.integers(min_value=300, max_value=86400)
invalid_jwt_lifetime_strategy = st.one_of(
    st.integers(min_value=-1000, max_value=299),
    st.integers(min_value=86401, max_value=1000000)
)

valid_port_strategy = st.integers(min_value=1, max_value=65535)
invalid_port_strategy = st.one_of(
    st.integers(min_value=-1000, max_value=0),
    st.integers(min_value=65536, max_value=100000)
)


class TestConfigurationValidationProperty:
    """
    Property 28: Configuration Validation on Startup
    
    For any missing required configuration variable, the application should fail
    to start with a clear error message.
    
    Validates: Requirements 12.4, 12.5
    """

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy
    )
    def test_property_valid_required_config_succeeds(
        self,
        database_url: str,
        secret_key: str
    ) -> None:
        """
        Property: For any valid required configuration, Settings should initialize successfully.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        
        # Should not raise any exception
        settings = Settings()
        
        assert settings.database_url == database_url
        assert settings.secret_key == secret_key

    @settings(max_examples=100)
    @given(secret_key=valid_secret_key_strategy)
    def test_property_missing_database_url_fails(self, secret_key: str) -> None:
        """
        Property: For any configuration missing DATABASE_URL, Settings initialization should fail.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        # Save and clear environment
        original_env = os.environ.copy()
        os.environ.clear()
        os.environ['TESTING'] = '1'
        
        try:
            os.environ["SECRET_KEY"] = secret_key
            # DATABASE_URL is intentionally not set
            
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            
            # Verify the error is about the missing database_url field
            errors = exc_info.value.errors()
            assert any(error["loc"] == ("database_url",) for error in errors)
            assert any(error["type"] == "missing" for error in errors)
        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(original_env)

    @settings(max_examples=100)
    @given(database_url=valid_database_url_strategy)
    def test_property_missing_secret_key_fails(self, database_url: str) -> None:
        """
        Property: For any configuration missing SECRET_KEY, Settings initialization should fail.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        # Save and clear environment
        original_env = os.environ.copy()
        os.environ.clear()
        os.environ['TESTING'] = '1'
        
        try:
            os.environ["DATABASE_URL"] = database_url
            # SECRET_KEY is intentionally not set
            
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            
            # Verify the error is about the missing secret_key field
            errors = exc_info.value.errors()
            assert any(error["loc"] == ("secret_key",) for error in errors)
            assert any(error["type"] == "missing" for error in errors)
        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(original_env)

    @settings(max_examples=100)
    @given(
        invalid_database_url=invalid_database_url_strategy,
        secret_key=valid_secret_key_strategy
    )
    def test_property_invalid_database_url_fails(
        self,
        invalid_database_url: str,
        secret_key: str
    ) -> None:
        """
        Property: For any invalid DATABASE_URL format, Settings initialization should fail with clear error.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = invalid_database_url
        os.environ["SECRET_KEY"] = secret_key
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify the error is about the database_url field
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("database_url",) for error in errors)

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        invalid_secret_key=invalid_secret_key_strategy
    )
    def test_property_short_secret_key_fails(
        self,
        database_url: str,
        invalid_secret_key: str
    ) -> None:
        """
        Property: For any SECRET_KEY shorter than 32 characters, Settings initialization should fail.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = invalid_secret_key
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify the error is about the secret_key field
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("secret_key",) for error in errors)

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy,
        jwt_lifetime=valid_jwt_lifetime_strategy
    )
    def test_property_valid_jwt_lifetime_succeeds(
        self,
        database_url: str,
        secret_key: str,
        jwt_lifetime: int
    ) -> None:
        """
        Property: For any valid JWT_LIFETIME_SECONDS (300-86400), Settings should initialize successfully.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        os.environ["JWT_LIFETIME_SECONDS"] = str(jwt_lifetime)
        
        settings = Settings()
        
        assert settings.jwt_lifetime_seconds == jwt_lifetime

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy,
        invalid_jwt_lifetime=invalid_jwt_lifetime_strategy
    )
    def test_property_invalid_jwt_lifetime_fails(
        self,
        database_url: str,
        secret_key: str,
        invalid_jwt_lifetime: int
    ) -> None:
        """
        Property: For any JWT_LIFETIME_SECONDS outside valid range, Settings initialization should fail.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        os.environ["JWT_LIFETIME_SECONDS"] = str(invalid_jwt_lifetime)
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify the error is about the jwt_lifetime_seconds field
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("jwt_lifetime_seconds",) for error in errors)

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy,
        port=valid_port_strategy
    )
    def test_property_valid_port_succeeds(
        self,
        database_url: str,
        secret_key: str,
        port: int
    ) -> None:
        """
        Property: For any valid PORT (1-65535), Settings should initialize successfully.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        os.environ["PORT"] = str(port)
        
        settings = Settings()
        
        assert settings.port == port

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy,
        invalid_port=invalid_port_strategy
    )
    def test_property_invalid_port_fails(
        self,
        database_url: str,
        secret_key: str,
        invalid_port: int
    ) -> None:
        """
        Property: For any PORT outside valid range (1-65535), Settings initialization should fail.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        os.environ["PORT"] = str(invalid_port)
        
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        # Verify the error is about the port field
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("port",) for error in errors)

    @settings(max_examples=100)
    @given(
        database_url=valid_database_url_strategy,
        secret_key=valid_secret_key_strategy,
        max_size=st.integers(min_value=1, max_value=50)
    )
    def test_property_max_image_size_bytes_calculation(
        self,
        database_url: str,
        secret_key: str,
        max_size: int
    ) -> None:
        """
        Property: For any MAX_IMAGE_SIZE_MB, max_image_size_bytes should equal MB * 1024 * 1024.
        
        Feature: laravel-to-fastapi-migration, Property 28: Configuration Validation on Startup
        """
        os.environ["DATABASE_URL"] = database_url
        os.environ["SECRET_KEY"] = secret_key
        os.environ["MAX_IMAGE_SIZE_MB"] = str(max_size)
        
        settings = Settings()
        
        expected_bytes = max_size * 1024 * 1024
        assert settings.max_image_size_bytes == expected_bytes
