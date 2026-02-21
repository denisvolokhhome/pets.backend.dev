"""
Property-based tests for API contract validation.

These tests verify that the FastAPI implementation maintains consistent
API contracts including JSON response formats, URL prefixes, and compatibility
with the Laravel implementation.
"""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.breed import Breed
from app.models.pet import Pet
from app.models.breeding import Breeding
from app.models.location import Location


@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    endpoint_path=st.sampled_from([
        "/api/breeds/",
        "/api/breedings/",
        "/api/pets/",
        "/api/locations/",
        "/health",
        "/"
    ])
)
async def test_property_json_response_format(
    endpoint_path: str,
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
):
    """
    Property 2: JSON Response Format
    
    For any API endpoint, all responses should have Content-Type: application/json.
    
    Feature: laravel-to-fastapi-migration, Property 2: JSON Response Format
    Validates: Requirements 1.5
    """
    # Determine if endpoint requires authentication
    requires_auth = endpoint_path.startswith("/api/pets") or endpoint_path.startswith("/api/locations")
    
    # Make request with or without auth, following redirects
    if requires_auth:
        response = await async_client.get(endpoint_path, headers=auth_headers, follow_redirects=True)
    else:
        response = await async_client.get(endpoint_path, follow_redirects=True)
    
    # Verify Content-Type header contains application/json
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type.lower(), (
        f"Expected JSON response for {endpoint_path}, got {content_type}"
    )
    
    # Verify response can be parsed as JSON
    try:
        response.json()
    except Exception as e:
        pytest.fail(f"Response from {endpoint_path} is not valid JSON: {e}")


@pytest.mark.asyncio
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    breed_name=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs", "Cc"))),
)
async def test_property_json_response_format_post_requests(
    breed_name: str,
    async_client: AsyncClient,
):
    """
    Property 2: JSON Response Format (POST requests)
    
    For any API endpoint receiving POST requests, responses should have Content-Type: application/json.
    
    Feature: laravel-to-fastapi-migration, Property 2: JSON Response Format
    Validates: Requirements 1.5
    """
    # Test POST request to breeds endpoint (public endpoint)
    response = await async_client.post(
        "/api/breeds",
        json={
            "name": breed_name,
            "code": "TEST",
            "group": "Test Group"
        }
    )
    
    # Verify Content-Type header contains application/json
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type.lower(), (
        f"Expected JSON response for POST /api/breeds, got {content_type}"
    )
    
    # Verify response can be parsed as JSON
    try:
        response.json()
    except Exception as e:
        pytest.fail(f"Response from POST /api/breeds is not valid JSON: {e}")


@pytest.mark.asyncio
async def test_property_json_response_format_error_responses(
    async_client: AsyncClient,
):
    """
    Property 2: JSON Response Format (Error responses)
    
    For any API endpoint returning errors, responses should have Content-Type: application/json.
    
    Feature: laravel-to-fastapi-migration, Property 2: JSON Response Format
    Validates: Requirements 1.5
    """
    # Test 404 error
    response = await async_client.get("/api/breeds/999999")
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type.lower()
    assert response.status_code == 404
    
    # Test 401 error (unauthorized)
    response = await async_client.get("/api/pets")
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type.lower()
    assert response.status_code == 401
    
    # Test 422 error (validation error)
    response = await async_client.post("/api/breeds", json={"invalid": "data"})
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type.lower()
    assert response.status_code == 422



@pytest.mark.asyncio
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    resource=st.sampled_from(["pets", "breeds", "breedings", "locations"])
)
async def test_property_url_prefix_consistency(
    resource: str,
    async_client: AsyncClient,
):
    """
    Property 27: URL Prefix Consistency
    
    For all API endpoints, the URL path should start with /api/.
    
    Feature: laravel-to-fastapi-migration, Property 27: URL Prefix Consistency
    Validates: Requirements 13.6
    """
    # Construct endpoint path with trailing slash to avoid redirects
    endpoint_path = f"/api/{resource}/"
    
    # Make request (some endpoints may require auth, but we're just checking URL structure)
    response = await async_client.get(endpoint_path, follow_redirects=True)
    
    # Verify the endpoint exists (not 404) or requires auth (401)
    # The key is that the URL structure is recognized
    # 307 redirects are acceptable (e.g., /api/pets -> /api/pets/)
    assert response.status_code in [200, 401, 403, 307], (
        f"Endpoint {endpoint_path} returned unexpected status {response.status_code}. "
        f"Expected 200 (success), 401 (auth required), 403 (forbidden), or 307 (redirect)"
    )


@pytest.mark.asyncio
async def test_property_url_prefix_consistency_all_routers(
    async_client: AsyncClient,
):
    """
    Property 27: URL Prefix Consistency (All routers)
    
    Verify that all registered routers use the /api/ prefix.
    
    Feature: laravel-to-fastapi-migration, Property 27: URL Prefix Consistency
    Validates: Requirements 13.6
    """
    from app.main import app
    
    # Get all routes from the FastAPI app
    api_routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            path = route.path
            # Exclude special routes like /health, /, /docs, /redoc, /openapi.json
            if path not in ["/", "/health", "/api/docs", "/api/redoc", "/api/openapi.json", "/storage/{path:path}"]:
                # Check if it's an API route (not a special route)
                if not path.startswith("/api/") and path not in ["/openapi.json", "/docs", "/redoc"]:
                    api_routes.append(path)
    
    # All API routes should start with /api/
    for route_path in api_routes:
        assert route_path.startswith("/api/") or route_path in ["/", "/health"], (
            f"Route {route_path} does not start with /api/ prefix"
        )


@pytest.mark.asyncio
async def test_property_url_prefix_consistency_specific_endpoints(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
):
    """
    Property 27: URL Prefix Consistency (Specific endpoints)
    
    Test specific known endpoints to ensure they follow the /api/ prefix convention.
    
    Feature: laravel-to-fastapi-migration, Property 27: URL Prefix Consistency
    Validates: Requirements 13.6
    """
    # Test various endpoints
    endpoints = [
        ("/api/breeds", False),  # (path, requires_auth)
        ("/api/breedings", False),
        ("/api/pets", True),
        ("/api/locations", True),
        ("/api/auth/register", False),
    ]
    
    for endpoint_path, requires_auth in endpoints:
        # Verify path starts with /api/
        assert endpoint_path.startswith("/api/"), (
            f"Endpoint {endpoint_path} does not start with /api/"
        )
        
        # Make request to verify endpoint exists
        if requires_auth:
            response = await async_client.get(endpoint_path, headers=auth_headers)
        else:
            response = await async_client.get(endpoint_path)
        
        # Should not be 404 (endpoint should exist)
        assert response.status_code != 404, (
            f"Endpoint {endpoint_path} returned 404 - endpoint does not exist"
        )



@pytest.mark.asyncio
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    breed_name=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs", "Cc"))),
    breed_code=st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=("Cs", "Cc"))),
    breed_group=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs", "Cc"))),
)
async def test_property_api_contract_consistency_breed_creation(
    breed_name: str,
    breed_code: str,
    breed_group: str,
    async_client: AsyncClient,
):
    """
    Property 1: API Contract Consistency
    
    For any breed creation request, the FastAPI response format should match
    the Laravel response format (same fields, same structure).
    
    Feature: laravel-to-fastapi-migration, Property 1: API Contract Consistency
    Validates: Requirements 1.3, 13.7
    """
    # Create breed
    response = await async_client.post(
        "/api/breeds",
        json={
            "name": breed_name,
            "code": breed_code,
            "group": breed_group
        }
    )
    
    # If successful, verify response structure matches Laravel contract
    if response.status_code == 201:
        data = response.json()
        
        # Verify required fields are present (Laravel contract)
        assert "id" in data, "Response missing 'id' field"
        assert "name" in data, "Response missing 'name' field"
        assert "code" in data, "Response missing 'code' field"
        assert "group" in data, "Response missing 'group' field"
        assert "created_at" in data, "Response missing 'created_at' field"
        assert "updated_at" in data, "Response missing 'updated_at' field"
        
        # Verify field values match input
        assert data["name"] == breed_name
        assert data["code"] == breed_code
        assert data["group"] == breed_group
        
        # Verify ID is an integer (Laravel uses integer IDs for breeds)
        assert isinstance(data["id"], int), f"Expected integer ID, got {type(data['id'])}"


@pytest.mark.asyncio
async def test_property_api_contract_consistency_breed_list(
    async_client: AsyncClient,
    test_breed: Breed,
):
    """
    Property 1: API Contract Consistency (List endpoint)
    
    For any breed list request, the FastAPI response format should match
    the Laravel response format.
    
    Feature: laravel-to-fastapi-migration, Property 1: API Contract Consistency
    Validates: Requirements 1.3, 13.7
    """
    # List breeds
    response = await async_client.get("/api/breeds", follow_redirects=True)
    
    assert response.status_code == 200
    data = response.json()
    
    # Response should be a list
    assert isinstance(data, list), "Expected list response"
    
    # If there are breeds, verify structure
    if len(data) > 0:
        breed = data[0]
        
        # Verify required fields are present (Laravel contract)
        assert "id" in breed, "Breed missing 'id' field"
        assert "name" in breed, "Breed missing 'name' field"
        assert "code" in breed, "Breed missing 'code' field"
        assert "group" in breed, "Breed missing 'group' field"
        assert "created_at" in breed, "Breed missing 'created_at' field"
        assert "updated_at" in breed, "Breed missing 'updated_at' field"


@pytest.mark.asyncio
async def test_property_api_contract_consistency_pet_creation(
    async_client: AsyncClient,
    test_user: User,
    test_breed: Breed,
    auth_headers: dict,
):
    """
    Property 1: API Contract Consistency (Pet creation)
    
    For any pet creation request, the FastAPI response format should match
    the Laravel response format.
    
    Feature: laravel-to-fastapi-migration, Property 1: API Contract Consistency
    Validates: Requirements 1.3, 13.7
    """
    # Create pet
    response = await async_client.post(
        "/api/pets",
        json={
            "name": "Test Pet",
            "breed_id": test_breed.id,
            "date_of_birth": "2024-01-01",
            "gender": "Male",
            "is_puppy": True
        },
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify required fields are present (Laravel contract)
    # Pets use UUID in both Laravel and FastAPI
    assert "id" in data, "Response missing 'id' field"
    assert "user_id" in data, "Response missing 'user_id' field"
    assert "name" in data, "Response missing 'name' field"
    assert "breed_id" in data, "Response missing 'breed_id' field"
    assert "date_of_birth" in data, "Response missing 'date_of_birth' field"
    assert "gender" in data, "Response missing 'gender' field"
    assert "is_puppy" in data, "Response missing 'is_puppy' field"
    assert "is_deleted" in data, "Response missing 'is_deleted' field"
    assert "created_at" in data, "Response missing 'created_at' field"
    assert "updated_at" in data, "Response missing 'updated_at' field"
    
    # Verify field values
    assert data["name"] == "Test Pet"
    assert data["is_deleted"] is False  # New pets should not be deleted
    assert data["user_id"] == str(test_user.id)  # UUID as string


@pytest.mark.asyncio
async def test_property_api_contract_consistency_error_responses(
    async_client: AsyncClient,
):
    """
    Property 1: API Contract Consistency (Error responses)
    
    For any error response, the FastAPI format should be consistent
    with standard error response structure.
    
    Feature: laravel-to-fastapi-migration, Property 1: API Contract Consistency
    Validates: Requirements 1.3, 13.7
    """
    # Test 404 error
    response = await async_client.get("/api/breeds/999999")
    assert response.status_code == 404
    data = response.json()
    
    # Error responses should have 'detail' field
    assert "detail" in data, "Error response missing 'detail' field"
    
    # Test 422 validation error
    response = await async_client.post("/api/breeds", json={"invalid": "data"})
    assert response.status_code == 422
    data = response.json()
    
    # Validation errors should have 'detail' field
    assert "detail" in data, "Validation error response missing 'detail' field"
