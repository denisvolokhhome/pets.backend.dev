"""Integration tests for /api/services endpoints.

Tests:
- POST /api/services — happy path, price_from > price_to → 422, foreign location → 403
- GET /api/services — returns only own non-deleted services
- PUT /api/services/{id} — non-owner → 403
- DELETE /api/services/{id} — soft delete; absent from subsequent list; non-owner → 403
- GET /api/services/search — basic smoke test
- GET /api/services/provider/{user_id}/public — correct response shape
"""

import uuid
import pytest
from contextvars import ContextVar
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.location import Location
from app.models.service import Service, service_locations
from app.models.service_category import ServiceCategory
from app.models.user import User


# ─── Context variable for per-request user switching ─────────────────────────

_current_test_user: ContextVar[User] = ContextVar("_current_test_user", default=None)


# ─── Shared client factory ────────────────────────────────────────────────────


def _make_user_aware_client(transport, base_url: str, user: User):
    """Return an AsyncClient subclass that injects `user` into the context var."""

    class UserAwareClient(AsyncClient):
        def __init__(self, *args, _user=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._user = _user

        async def request(self, *args, **kwargs):
            token = _current_test_user.set(self._user)
            try:
                return await super().request(*args, **kwargs)
            finally:
                _current_test_user.reset(token)

    return UserAwareClient(transport=transport, base_url=base_url, _user=user)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def cleanup_overrides():
    yield
    app.dependency_overrides.clear()
    _current_test_user.set(None)


@pytest.fixture
async def service_provider(async_session: AsyncSession) -> User:
    """Create a service provider user."""
    import bcrypt

    hashed = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
    user = User(
        email=f"sp-{uuid.uuid4()}@example.com",
        hashed_password=hashed,
        name="Test Service Provider",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=False,
        account_type="service",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def other_service_provider(async_session: AsyncSession) -> User:
    """Create a second service provider user (for ownership tests)."""
    import bcrypt

    hashed = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
    user = User(
        email=f"sp-other-{uuid.uuid4()}@example.com",
        hashed_password=hashed,
        name="Other Service Provider",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=False,
        account_type="service",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def grooming_category(async_session: AsyncSession) -> ServiceCategory:
    """Seed an active service category."""
    cat = ServiceCategory(
        name=f"Grooming-{uuid.uuid4().hex[:6]}",
        slug=f"grooming-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    async_session.add(cat)
    await async_session.commit()
    await async_session.refresh(cat)
    return cat


@pytest.fixture
async def provider_location(
    async_session: AsyncSession, service_provider: User
) -> Location:
    """Create a location owned by the service provider."""
    loc = Location(
        user_id=service_provider.id,
        name="Provider HQ",
        address1="1 Provider St",
        city="Providertown",
        state="PT",
        country="US",
        zipcode="10001",
        location_type="service",
    )
    async_session.add(loc)
    await async_session.commit()
    await async_session.refresh(loc)
    return loc


@pytest.fixture
async def other_location(
    async_session: AsyncSession, other_service_provider: User
) -> Location:
    """Create a location owned by the OTHER service provider."""
    loc = Location(
        user_id=other_service_provider.id,
        name="Other Provider HQ",
        address1="2 Other St",
        city="Othertown",
        state="OT",
        country="US",
        zipcode="20002",
        location_type="service",
    )
    async_session.add(loc)
    await async_session.commit()
    await async_session.refresh(loc)
    return loc


@pytest.fixture
async def sp_client(
    async_session: AsyncSession, service_provider: User
) -> AsyncClient:
    """Authenticated client acting as service_provider."""

    async def override_session():
        yield async_session

    async def override_user():
        user = _current_test_user.get()
        return user if user is not None else service_provider

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[current_active_user] = override_user

    transport = ASGITransport(app=app)
    async with _make_user_aware_client(
        transport, "http://test", service_provider
    ) as ac:
        yield ac


@pytest.fixture
async def other_sp_client(
    async_session: AsyncSession, other_service_provider: User
) -> AsyncClient:
    """Authenticated client acting as other_service_provider."""

    async def override_session():
        yield async_session

    async def override_user():
        user = _current_test_user.get()
        return user if user is not None else other_service_provider

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[current_active_user] = override_user

    transport = ASGITransport(app=app)
    async with _make_user_aware_client(
        transport, "http://test", other_service_provider
    ) as ac:
        yield ac


@pytest.fixture
async def public_client(async_session: AsyncSession) -> AsyncClient:
    """Unauthenticated client for public endpoints."""

    async def override_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Helper ───────────────────────────────────────────────────────────────────


async def _create_service(
    client: AsyncClient,
    category_id: int,
    location_id: int,
    title: str = "Test Service",
    price_from: float | None = None,
    price_to: float | None = None,
) -> dict:
    """POST /api/services and return the response JSON."""
    payload: dict = {
        "category_id": category_id,
        "title": title,
        "location_ids": [location_id],
    }
    if price_from is not None:
        payload["price_from"] = str(price_from)
    if price_to is not None:
        payload["price_to"] = str(price_to)
    response = await client.post("/api/services", json=payload)
    return response


# ─── POST /api/services ───────────────────────────────────────────────────────


class TestCreateService:
    """Tests for POST /api/services."""

    @pytest.mark.asyncio
    async def test_happy_path_creates_service(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Valid payload creates a service and returns 201.

        Validates: Requirements 7.3, 7.4
        """
        response = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "My Grooming Service"
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Grooming Service"
        assert data["category_id"] == grooming_category.id
        assert "id" in data
        assert data["is_deleted"] is False

    @pytest.mark.asyncio
    async def test_price_from_greater_than_price_to_returns_422(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """price_from > price_to is rejected with 422.

        Validates: Requirements 7.8
        """
        response = await _create_service(
            sp_client,
            grooming_category.id,
            provider_location.id,
            price_from=100.00,
            price_to=50.00,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_price_from_equal_to_price_to_is_accepted(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """price_from == price_to is valid.

        Validates: Requirements 7.8
        """
        response = await _create_service(
            sp_client,
            grooming_category.id,
            provider_location.id,
            price_from=50.00,
            price_to=50.00,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_location_not_owned_by_user_returns_403(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        other_location: Location,
    ):
        """Using a location owned by another user returns 403.

        Validates: Requirements 7.6, 7.7
        """
        response = await _create_service(
            sp_client, grooming_category.id, other_location.id
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_location_ids_returns_422(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
    ):
        """Omitting location_ids (or empty list) returns 422."""
        payload = {
            "category_id": grooming_category.id,
            "title": "No Location Service",
            "location_ids": [],
        }
        response = await sp_client.post("/api/services", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_category_id_returns_422(
        self,
        sp_client: AsyncClient,
        provider_location: Location,
    ):
        """Non-existent category_id returns 422."""
        payload = {
            "category_id": 999999,
            "title": "Bad Category Service",
            "location_ids": [provider_location.id],
        }
        response = await sp_client.post("/api/services", json=payload)
        assert response.status_code == 422


# ─── GET /api/services ────────────────────────────────────────────────────────


class TestListServices:
    """Tests for GET /api/services."""

    @pytest.mark.asyncio
    async def test_returns_own_services(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """GET /api/services returns the authenticated user's services.

        Validates: Requirements 7.3
        """
        # Create two services
        r1 = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Service A"
        )
        r2 = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Service B"
        )
        assert r1.status_code == 201
        assert r2.status_code == 201

        response = await sp_client.get("/api/services")
        assert response.status_code == 200
        data = response.json()

        titles = [item["title"] for item in data["items"]]
        assert "Service A" in titles
        assert "Service B" in titles

    @pytest.mark.asyncio
    async def test_does_not_return_other_users_services(
        self,
        sp_client: AsyncClient,
        other_sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
        other_location: Location,
    ):
        """GET /api/services does not return services owned by other users."""
        # Create service for other provider
        r = await _create_service(
            other_sp_client, grooming_category.id, other_location.id, "Other Provider Service"
        )
        assert r.status_code == 201
        other_service_id = r.json()["id"]

        # List services for first provider
        response = await sp_client.get("/api/services")
        assert response.status_code == 200
        data = response.json()

        ids = [item["id"] for item in data["items"]]
        assert other_service_id not in ids

    @pytest.mark.asyncio
    async def test_soft_deleted_services_excluded(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Soft-deleted services do not appear in GET /api/services.

        Validates: Requirements 7.5
        """
        # Create and then delete a service
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "To Be Deleted"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        delete_r = await sp_client.delete(f"/api/services/{service_id}")
        assert delete_r.status_code == 204

        # Verify it's gone from the list
        list_r = await sp_client.get("/api/services")
        assert list_r.status_code == 200
        ids = [item["id"] for item in list_r.json()["items"]]
        assert service_id not in ids

    @pytest.mark.asyncio
    async def test_response_has_pagination_envelope(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Response contains items, total, page, page_size fields."""
        await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Envelope Test"
        )
        response = await sp_client.get("/api/services")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data


# ─── PUT /api/services/{id} ───────────────────────────────────────────────────


class TestUpdateService:
    """Tests for PUT /api/services/{id}."""

    @pytest.mark.asyncio
    async def test_owner_can_update_service(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Service owner can update their service."""
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Original Title"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        update_r = await sp_client.put(
            f"/api/services/{service_id}",
            json={"title": "Updated Title"},
        )
        assert update_r.status_code == 200
        assert update_r.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_non_owner_update_returns_403(
        self,
        sp_client: AsyncClient,
        other_sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Non-owner attempting to update a service receives 403.

        Validates: Requirements 7.6, 7.7
        """
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Owner's Service"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        update_r = await other_sp_client.put(
            f"/api/services/{service_id}",
            json={"title": "Hacked Title"},
        )
        assert update_r.status_code == 403

    @pytest.mark.asyncio
    async def test_update_nonexistent_service_returns_404(
        self, sp_client: AsyncClient
    ):
        """Updating a non-existent service returns 404."""
        fake_id = str(uuid.uuid4())
        response = await sp_client.put(
            f"/api/services/{fake_id}",
            json={"title": "Ghost Service"},
        )
        assert response.status_code == 404


# ─── DELETE /api/services/{id} ────────────────────────────────────────────────


class TestDeleteService:
    """Tests for DELETE /api/services/{id}."""

    @pytest.mark.asyncio
    async def test_soft_delete_returns_204(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Deleting a service returns 204 No Content.

        Validates: Requirements 7.5
        """
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Delete Me"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        delete_r = await sp_client.delete(f"/api/services/{service_id}")
        assert delete_r.status_code == 204

    @pytest.mark.asyncio
    async def test_deleted_service_absent_from_list(
        self,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """After soft-delete, the service no longer appears in GET /api/services.

        Validates: Requirements 7.5
        """
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Soft Delete Test"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        await sp_client.delete(f"/api/services/{service_id}")

        list_r = await sp_client.get("/api/services")
        assert list_r.status_code == 200
        ids = [item["id"] for item in list_r.json()["items"]]
        assert service_id not in ids

    @pytest.mark.asyncio
    async def test_non_owner_delete_returns_403(
        self,
        sp_client: AsyncClient,
        other_sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Non-owner attempting to delete a service receives 403.

        Validates: Requirements 7.6, 7.7
        """
        create_r = await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Protected Service"
        )
        assert create_r.status_code == 201
        service_id = create_r.json()["id"]

        delete_r = await other_sp_client.delete(f"/api/services/{service_id}")
        assert delete_r.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_service_returns_404(
        self, sp_client: AsyncClient
    ):
        """Deleting a non-existent service returns 404."""
        fake_id = str(uuid.uuid4())
        response = await sp_client.delete(f"/api/services/{fake_id}")
        assert response.status_code == 404


# ─── GET /api/services/search ─────────────────────────────────────────────────


class TestSearchServices:
    """Smoke tests for GET /api/services/search."""

    @pytest.mark.asyncio
    async def test_search_returns_200_with_pagination_envelope(
        self, public_client: AsyncClient
    ):
        """Search endpoint returns 200 with the expected pagination envelope.

        Validates: Requirements 9.1, 9.7
        """
        response = await public_client.get("/api/services/search")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_search_with_category_slug_filter(
        self,
        public_client: AsyncClient,
        sp_client: AsyncClient,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Search can be filtered by category_slug.

        Validates: Requirements 9.1
        """
        # Create a service so there's something to find
        await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Searchable Service"
        )

        response = await public_client.get(
            f"/api/services/search?category_slug={grooming_category.slug}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_search_pagination_params_accepted(
        self, public_client: AsyncClient
    ):
        """Search accepts page and page_size query parameters."""
        response = await public_client.get("/api/services/search?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    @pytest.mark.asyncio
    async def test_search_is_public_no_auth_required(
        self, public_client: AsyncClient
    ):
        """Search endpoint is accessible without authentication."""
        response = await public_client.get("/api/services/search")
        assert response.status_code == 200


# ─── GET /api/services/provider/{user_id}/public ─────────────────────────────


class TestPublicProviderProfile:
    """Tests for GET /api/services/provider/{user_id}/public."""

    @pytest.mark.asyncio
    async def test_returns_correct_response_shape(
        self,
        public_client: AsyncClient,
        sp_client: AsyncClient,
        service_provider: User,
        grooming_category: ServiceCategory,
        provider_location: Location,
    ):
        """Public profile endpoint returns the expected response shape.

        Validates: Requirements 9.5
        """
        # Create a service so the provider has something to show
        await _create_service(
            sp_client, grooming_category.id, provider_location.id, "Public Service"
        )

        response = await public_client.get(
            f"/api/services/provider/{service_provider.id}/public"
        )
        assert response.status_code == 200
        data = response.json()

        # Verify required fields per Requirements 9.5
        assert "user_id" in data
        assert "provider_name" in data
        assert "categories" in data
        assert "services" in data
        assert "locations" in data
        assert isinstance(data["services"], list)
        assert isinstance(data["locations"], list)
        assert isinstance(data["categories"], list)

    @pytest.mark.asyncio
    async def test_returns_correct_user_id(
        self,
        public_client: AsyncClient,
        service_provider: User,
    ):
        """Public profile user_id matches the requested provider."""
        response = await public_client.get(
            f"/api/services/provider/{service_provider.id}/public"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(service_provider.id)

    @pytest.mark.asyncio
    async def test_nonexistent_provider_returns_404(
        self, public_client: AsyncClient
    ):
        """Requesting a non-existent provider returns 404."""
        fake_id = str(uuid.uuid4())
        response = await public_client.get(
            f"/api/services/provider/{fake_id}/public"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_service_account_returns_404(
        self,
        public_client: AsyncClient,
        async_session: AsyncSession,
    ):
        """Requesting a profile for a non-service-account user returns 404."""
        import bcrypt

        hashed = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
        breeder = User(
            email=f"breeder-{uuid.uuid4()}@example.com",
            hashed_password=hashed,
            name="Regular Breeder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
            account_type="breeder",
        )
        async_session.add(breeder)
        await async_session.commit()
        await async_session.refresh(breeder)

        response = await public_client.get(
            f"/api/services/provider/{breeder.id}/public"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_endpoint_is_public_no_auth_required(
        self,
        public_client: AsyncClient,
        service_provider: User,
    ):
        """Public profile endpoint is accessible without authentication."""
        response = await public_client.get(
            f"/api/services/provider/{service_provider.id}/public"
        )
        # 200 or 404 are both acceptable — the point is it's not 401/403
        assert response.status_code in (200, 404)
        assert response.status_code != 401
        assert response.status_code != 403
