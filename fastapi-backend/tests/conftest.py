"""Shared test fixtures and configuration."""

import pytest
from typing import Generator, AsyncGenerator
import os

# Set TESTING flag to prevent loading .env file
os.environ['TESTING'] = '1'

# Set up test environment BEFORE any imports
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://test:test@localhost:5432/test_db'
os.environ['SECRET_KEY'] = 'test_secret_key_at_least_32_characters_long_for_security'
os.environ['DEBUG'] = 'true'

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.schema import DefaultClause

from app.database import Base
from app.models import User


def _fix_string_server_defaults():
    """Convert string server_default values to text() expressions.
    
    Some models use plain strings for server_default (e.g. "gen_random_uuid()")
    which works with Alembic migrations but breaks Base.metadata.create_all
    with asyncpg because asyncpg treats them as literal string values.
    """
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.server_default is not None and isinstance(column.server_default.arg, str):
                val = column.server_default.arg
                # Only convert values that look like SQL expressions
                if val.endswith(")") or val.lower() in ("true", "false"):
                    column.server_default = DefaultClause(text(val))


@pytest.fixture(autouse=True)
def setup_test_env() -> Generator[None, None, None]:
    """Set up test environment variables before each test."""
    original_env = os.environ.copy()
    
    # Set TESTING flag
    os.environ['TESTING'] = '1'
    
    # Set required environment variables for testing
    os.environ['DATABASE_URL'] = 'postgresql+asyncpg://test:test@localhost:5432/test_db'
    os.environ['SECRET_KEY'] = 'test_secret_key_at_least_32_characters_long_for_security'
    
    # Reset the rate limiter between tests to prevent cross-test interference
    from app.middleware.rate_limiter import rate_limiter
    rate_limiter.requests.clear()
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Provide a clean environment for tests that need to test missing variables."""
    original_env = os.environ.copy()
    
    # Clear all environment variables except TESTING
    os.environ.clear()
    os.environ['TESTING'] = '1'
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session for tests."""
    # Use test database URL
    test_database_url = os.environ.get(
        'TEST_DATABASE_URL',
        'postgresql+asyncpg://test:test@localhost:5432/test_db'
    )
    
    engine = create_async_engine(
        test_database_url,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Enable PostGIS extension and create tables
    async with engine.begin() as conn:
        # Enable PostGIS extension for geospatial support
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        # Fix string server_defaults before creating tables
        _fix_string_server_defaults()
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()
    
    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_user(async_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_placeholder",
        name="Test User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user



@pytest.fixture
async def test_breed(async_session: AsyncSession):
    """Create a test breed."""
    from app.models.breed import Breed
    
    breed = Breed(
        name="Test Breed",
        kind="dog"
    )
    async_session.add(breed)
    await async_session.commit()
    await async_session.refresh(breed)
    return breed


@pytest.fixture
async def async_client(async_session: AsyncSession, test_user: User):
    """Create test client with database session and auth overrides."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.database import get_async_session
    from app.dependencies import current_active_user
    
    async def override_get_async_session():
        yield async_session
    
    async def override_current_active_user():
        return test_user
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[current_active_user] = override_current_active_user
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def unauthenticated_client(async_session: AsyncSession):
    """Create test client with database session override but NO auth override.
    
    Use this for tests that need to test the full authentication flow
    (registration, login, etc.) without pre-authenticated users.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.database import get_async_session
    
    async def override_get_async_session():
        yield async_session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(test_user: User):
    """Create authentication headers for test user."""
    # Since we're overriding the dependency, we don't need a real token
    # But we'll provide headers for consistency
    return {"Authorization": f"Bearer test_token_{test_user.id}"}




@pytest.fixture
async def test_breeder(async_session: AsyncSession) -> User:
    """Create a test breeder user."""
    import bcrypt
    
    # Hash password using bcrypt directly
    hashed_password = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode('utf-8')
    
    user = User(
        email="breeder@example.com",
        hashed_password=hashed_password,
        name="Test Breeder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_pet_seeker(async_session: AsyncSession) -> User:
    """Create a test pet seeker user."""
    import bcrypt
    
    # Hash password using bcrypt directly
    hashed_password = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode('utf-8')
    
    user = User(
        email="petseeker@example.com",
        hashed_password=hashed_password,
        name="Test Seeker",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=False
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_breeding(async_session: AsyncSession, test_breeder: User, test_breed) -> "Breeding":
    """Create a test breeding."""
    from app.models.breeding import Breeding
    from datetime import date
    
    breeding = Breeding(
        user_id=test_breeder.id,
        date_of_litter=date(2024, 3, 1),
        description="Test breeding",
        is_active=True,
        status="Started"
    )
    async_session.add(breeding)
    await async_session.commit()
    await async_session.refresh(breeding)
    return breeding


@pytest.fixture
async def test_offspring(async_session: AsyncSession, test_breeder: User, test_breed, test_breeding) -> "Offspring":
    """Create a test offspring."""
    from app.models.offspring import Offspring
    from datetime import date
    from decimal import Decimal
    
    offspring = Offspring(
        breeding_id=test_breeding.id,
        user_id=test_breeder.id,
        breed_id=test_breed.id,
        name="Test Puppy",
        gender="Male",
        date_of_birth=date(2024, 3, 1),
        status="Available",
        price=Decimal("1000.00"),
        description="A lovely test puppy",
        color_markings="Brown and white"
    )
    async_session.add(offspring)
    await async_session.commit()
    await async_session.refresh(offspring)
    return offspring
