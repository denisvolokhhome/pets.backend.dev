"""Integration tests for POST /api/auth/register/service-provider.

Tests:
- Happy path: valid registration creates user with account_type='service', is_breeder=False
- Category associations are stored
- Duplicate email → 400
- Zero categories → 422
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.models.service_category import ServiceCategory, user_service_categories
from app.models.user import User


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def client(async_session: AsyncSession):
    """Unauthenticated test client for registration tests."""

    async def override_get_async_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def grooming_category(async_session: AsyncSession) -> ServiceCategory:
    """Seed a single active service category for use in registration tests."""
    cat = ServiceCategory(
        name="Grooming",
        slug="grooming",
        description="Pet grooming services",
        is_active=True,
    )
    async_session.add(cat)
    await async_session.commit()
    await async_session.refresh(cat)
    return cat


@pytest.fixture
async def two_categories(async_session: AsyncSession) -> list[ServiceCategory]:
    """Seed two active service categories."""
    cats = [
        ServiceCategory(name="Dog Walking", slug="dog-walking", is_active=True),
        ServiceCategory(name="Cat Sitting", slug="cat-sitting", is_active=True),
    ]
    for cat in cats:
        async_session.add(cat)
    await async_session.commit()
    for cat in cats:
        await async_session.refresh(cat)
    return cats


@pytest.fixture
async def inactive_category(async_session: AsyncSession) -> ServiceCategory:
    """Seed an inactive service category."""
    cat = ServiceCategory(
        name="Deprecated Service",
        slug="deprecated-service",
        is_active=False,
    )
    async_session.add(cat)
    await async_session.commit()
    await async_session.refresh(cat)
    return cat


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestServiceProviderRegistrationHappyPath:
    """Happy-path tests for service provider registration."""

    @pytest.mark.asyncio
    async def test_register_returns_201(
        self, client: AsyncClient, grooming_category: ServiceCategory
    ):
        """Successful registration returns HTTP 201.

        Validates: Requirements 3.5, 3.7
        """
        payload = {
            "email": "provider@example.com",
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_register_sets_account_type_service(
        self,
        client: AsyncClient,
        grooming_category: ServiceCategory,
        async_session: AsyncSession,
    ):
        """Registered user has account_type='service'.

        Validates: Requirements 1.4, 3.5
        """
        payload = {
            "email": "sp_account_type@example.com",
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201

        # Verify in DB
        result = await async_session.execute(
            select(User).where(User.email == payload["email"])
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.account_type == "service"

    @pytest.mark.asyncio
    async def test_register_sets_is_breeder_false(
        self,
        client: AsyncClient,
        grooming_category: ServiceCategory,
        async_session: AsyncSession,
    ):
        """Registered service provider has is_breeder=False.

        Validates: Requirements 1.4, 3.5
        """
        payload = {
            "email": "sp_not_breeder@example.com",
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201

        result = await async_session.execute(
            select(User).where(User.email == payload["email"])
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.is_breeder is False

    @pytest.mark.asyncio
    async def test_register_stores_category_associations(
        self,
        client: AsyncClient,
        two_categories: list[ServiceCategory],
        async_session: AsyncSession,
    ):
        """Category associations are persisted in user_service_categories.

        Validates: Requirements 3.6
        """
        category_ids = [cat.id for cat in two_categories]
        payload = {
            "email": "sp_categories@example.com",
            "password": "SecurePass123!",
            "category_ids": category_ids,
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201

        # Fetch the created user
        result = await async_session.execute(
            select(User).where(User.email == payload["email"])
        )
        user = result.scalar_one_or_none()
        assert user is not None

        # Verify associations in the join table
        assoc_result = await async_session.execute(
            select(user_service_categories).where(
                user_service_categories.c.user_id == user.id
            )
        )
        rows = assoc_result.all()
        stored_category_ids = {row.category_id for row in rows}
        assert stored_category_ids == set(category_ids)

    @pytest.mark.asyncio
    async def test_register_with_optional_name(
        self,
        client: AsyncClient,
        grooming_category: ServiceCategory,
        async_session: AsyncSession,
    ):
        """Optional name field is stored when provided."""
        payload = {
            "email": "sp_with_name@example.com",
            "password": "SecurePass123!",
            "name": "Fluffy Paws Grooming",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201

        result = await async_session.execute(
            select(User).where(User.email == payload["email"])
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.name == "Fluffy Paws Grooming"

    @pytest.mark.asyncio
    async def test_register_response_contains_user_fields(
        self, client: AsyncClient, grooming_category: ServiceCategory
    ):
        """Response body contains expected user fields."""
        payload = {
            "email": "sp_response_shape@example.com",
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["email"] == payload["email"]
        assert data["is_active"] is True
        assert "hashed_password" not in data


class TestServiceProviderRegistrationErrors:
    """Error-case tests for service provider registration."""

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_400(
        self, client: AsyncClient, grooming_category: ServiceCategory
    ):
        """Registering with an already-used email returns 400.

        Validates: Requirements 3.5
        """
        payload = {
            "email": "duplicate_sp@example.com",
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }

        # First registration succeeds
        response1 = await client.post("/api/auth/register/service-provider", json=payload)
        assert response1.status_code == 201

        # Second registration with same email fails
        response2 = await client.post("/api/auth/register/service-provider", json=payload)
        assert response2.status_code == 400
        data = response2.json()
        assert "detail" in data
        assert "REGISTER_USER_ALREADY_EXISTS" in data["detail"]

    @pytest.mark.asyncio
    async def test_zero_categories_returns_422(self, client: AsyncClient):
        """Registering with an empty category_ids list returns 422.

        Validates: Requirements 3.3, 3.8
        """
        payload = {
            "email": "sp_no_cats@example.com",
            "password": "SecurePass123!",
            "category_ids": [],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_category_ids_field_returns_422(self, client: AsyncClient):
        """Omitting category_ids entirely returns 422."""
        payload = {
            "email": "sp_missing_cats@example.com",
            "password": "SecurePass123!",
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_category_id_returns_422(self, client: AsyncClient):
        """Providing a non-existent category_id returns 422."""
        payload = {
            "email": "sp_bad_cat@example.com",
            "password": "SecurePass123!",
            "category_ids": [999999],  # Does not exist
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_inactive_category_id_returns_422(
        self, client: AsyncClient, inactive_category: ServiceCategory
    ):
        """Providing an inactive category_id returns 422."""
        payload = {
            "email": "sp_inactive_cat@example.com",
            "password": "SecurePass123!",
            "category_ids": [inactive_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_password_returns_422(
        self, client: AsyncClient, grooming_category: ServiceCategory
    ):
        """Omitting password returns 422."""
        payload = {
            "email": "sp_no_pass@example.com",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_email_returns_422(
        self, client: AsyncClient, grooming_category: ServiceCategory
    ):
        """Omitting email returns 422."""
        payload = {
            "password": "SecurePass123!",
            "category_ids": [grooming_category.id],
        }
        response = await client.post("/api/auth/register/service-provider", json=payload)
        assert response.status_code == 422
