"""Integration tests for GET /api/service-categories endpoint.

Tests:
- Returns only active categories
- Deactivated categories are excluded from the response
"""

import pytest
from contextvars import ContextVar
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.models.service_category import ServiceCategory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def client(async_session: AsyncSession):
    """Unauthenticated test client — service-categories is a public endpoint."""

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
async def active_category(async_session: AsyncSession) -> ServiceCategory:
    """Create a single active service category."""
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
async def inactive_category(async_session: AsyncSession) -> ServiceCategory:
    """Create a single inactive service category."""
    cat = ServiceCategory(
        name="Inactive Service",
        slug="inactive-service",
        description="This category is deactivated",
        is_active=False,
    )
    async_session.add(cat)
    await async_session.commit()
    await async_session.refresh(cat)
    return cat


@pytest.fixture
async def mixed_categories(async_session: AsyncSession) -> dict:
    """Create a mix of active and inactive categories; return their IDs."""
    active_cats = [
        ServiceCategory(name="Dog Walking", slug="dog-walking", is_active=True),
        ServiceCategory(name="Cat Sitting", slug="cat-sitting", is_active=True),
        ServiceCategory(name="Pet Training", slug="pet-training", is_active=True),
    ]
    inactive_cats = [
        ServiceCategory(name="Old Service A", slug="old-service-a", is_active=False),
        ServiceCategory(name="Old Service B", slug="old-service-b", is_active=False),
    ]
    for cat in active_cats + inactive_cats:
        async_session.add(cat)
    await async_session.commit()
    for cat in active_cats + inactive_cats:
        await async_session.refresh(cat)

    return {
        "active_ids": {cat.id for cat in active_cats},
        "inactive_ids": {cat.id for cat in inactive_cats},
        "active_slugs": {cat.slug for cat in active_cats},
        "inactive_slugs": {cat.slug for cat in inactive_cats},
    }


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestServiceCategoriesEndpoint:
    """Tests for GET /api/service-categories."""

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list_when_no_categories(
        self, client: AsyncClient
    ):
        """Endpoint returns 200 and an empty list when no categories exist."""
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_active_category(
        self, client: AsyncClient, active_category: ServiceCategory
    ):
        """A single active category is returned in the response."""
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 1
        ids = [item["id"] for item in data]
        assert active_category.id in ids

    @pytest.mark.asyncio
    async def test_active_category_has_expected_fields(
        self, client: AsyncClient, active_category: ServiceCategory
    ):
        """Each returned category contains the required fields."""
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        data = response.json()

        # Find our category in the response
        cat = next((item for item in data if item["id"] == active_category.id), None)
        assert cat is not None, "Active category not found in response"

        assert cat["id"] == active_category.id
        assert cat["name"] == active_category.name
        assert cat["slug"] == active_category.slug
        assert cat["is_active"] is True

    @pytest.mark.asyncio
    async def test_deactivated_category_excluded(
        self,
        client: AsyncClient,
        active_category: ServiceCategory,
        inactive_category: ServiceCategory,
    ):
        """
        A deactivated category (is_active=False) must NOT appear in the response.

        Validates: Requirements 2.4
        """
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        data = response.json()

        ids = [item["id"] for item in data]

        # Active category is present
        assert active_category.id in ids

        # Inactive category is absent
        assert inactive_category.id not in ids

    @pytest.mark.asyncio
    async def test_only_active_categories_returned_from_mixed_set(
        self, client: AsyncClient, mixed_categories: dict
    ):
        """
        When both active and inactive categories exist, only active ones are returned.

        Validates: Requirements 2.3, 2.4
        """
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        data = response.json()

        returned_ids = {item["id"] for item in data}
        returned_slugs = {item["slug"] for item in data}

        # All active categories are present
        for active_id in mixed_categories["active_ids"]:
            assert active_id in returned_ids

        # No inactive categories are present
        for inactive_id in mixed_categories["inactive_ids"]:
            assert inactive_id not in returned_ids

        # Verify by slug as well
        for inactive_slug in mixed_categories["inactive_slugs"]:
            assert inactive_slug not in returned_slugs

    @pytest.mark.asyncio
    async def test_all_returned_categories_have_is_active_true(
        self, client: AsyncClient, mixed_categories: dict
    ):
        """
        Every item in the response must have is_active=True.

        Validates: Requirements 2.4 (Property 7)
        """
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        data = response.json()

        for item in data:
            assert item["is_active"] is True, (
                f"Category {item['id']} ({item['slug']}) has is_active=False "
                "but was returned by the endpoint"
            )

    @pytest.mark.asyncio
    async def test_endpoint_is_public_no_auth_required(self, client: AsyncClient):
        """The endpoint must be accessible without authentication."""
        # client fixture has no auth override — this verifies public access
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_response_is_a_list(self, client: AsyncClient, active_category: ServiceCategory):
        """The response body must be a JSON array."""
        response = await client.get("/api/service-categories/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
