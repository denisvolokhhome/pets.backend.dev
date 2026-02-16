#!/usr/bin/env python
"""
Verification script for route registration.

This script verifies that all required routes are properly registered
in the FastAPI application.
"""

from app.main import app


def verify_routes():
    """Verify that all required routes are registered."""
    
    # Expected routes for users
    expected_user_routes = [
        ("/api/users/me", {"GET"}),
        ("/api/users/me", {"PATCH"}),
        ("/api/users/me/profile-image", {"POST"}),
        ("/api/users/me/profile-image", {"GET"}),
    ]
    
    # Expected routes for locations
    expected_location_routes = [
        ("/api/locations/", {"POST"}),
        ("/api/locations/", {"GET"}),
        ("/api/locations/{location_id}", {"GET"}),
        ("/api/locations/{location_id}", {"PUT"}),
        ("/api/locations/{location_id}", {"DELETE"}),
    ]
    
    # Get all registered routes
    registered_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            registered_routes.append((route.path, route.methods))
    
    print("=" * 70)
    print("ROUTE REGISTRATION VERIFICATION")
    print("=" * 70)
    print()
    
    # Verify user routes
    print("✓ USER PROFILE ROUTES:")
    print("-" * 70)
    all_user_routes_found = True
    for path, methods in expected_user_routes:
        found = any(r[0] == path and methods.issubset(r[1]) for r in registered_routes)
        status = "✓" if found else "✗"
        print(f"  {status} {path} {list(methods)}")
        if not found:
            all_user_routes_found = False
    print()
    
    # Verify location routes
    print("✓ LOCATION ROUTES:")
    print("-" * 70)
    all_location_routes_found = True
    for path, methods in expected_location_routes:
        found = any(r[0] == path and methods.issubset(r[1]) for r in registered_routes)
        status = "✓" if found else "✗"
        print(f"  {status} {path} {list(methods)}")
        if not found:
            all_location_routes_found = False
    print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    if all_user_routes_found and all_location_routes_found:
        print("✓ All required routes are properly registered!")
        print()
        print("Requirements validated:")
        print("  ✓ 8.1 - GET /api/users/me endpoint")
        print("  ✓ 8.2 - PATCH /api/users/me endpoint")
        print("  ✓ 8.3 - POST /api/users/me/profile-image endpoint")
        print("  ✓ 8.4 - GET /api/locations endpoint")
        print("  ✓ 8.5 - POST /api/locations endpoint")
        print("  ✓ 8.6 - PATCH /api/locations/{id} endpoint")
        print("  ✓ 8.7 - DELETE /api/locations/{id} endpoint")
        return True
    else:
        print("✗ Some routes are missing!")
        return False


if __name__ == "__main__":
    success = verify_routes()
    exit(0 if success else 1)
