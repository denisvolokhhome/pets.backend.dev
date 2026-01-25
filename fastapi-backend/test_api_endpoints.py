#!/usr/bin/env python3
"""
Manual API endpoint testing script for user profile and settings feature.
This script tests the backend API endpoints to verify they are working correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from httpx import AsyncClient
from app.main import app
from app.database import get_async_session
from sqlalchemy import text


async def test_endpoints():
    """Test all user profile and location endpoints."""
    
    print("=" * 80)
    print("Backend API Endpoint Testing")
    print("=" * 80)
    print()
    
    # Test database connection
    print("1. Testing database connection...")
    try:
        async for session in get_async_session():
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            print("   ✓ Database connection successful")
            break
    except Exception as e:
        print(f"   ✗ Database connection failed: {e}")
        return False
    
    print()
    
    # Create test client
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        
        # Test 1: Register a test user
        print("2. Testing user registration...")
        register_data = {
            "email": "test_checkpoint@example.com",
            "password": "TestPassword123!",
            "is_active": True,
            "is_superuser": False,
            "is_verified": True
        }
        
        try:
            response = await client.post("/api/auth/register", json=register_data)
            if response.status_code == 201:
                user_data = response.json()
                print(f"   ✓ User registered successfully (ID: {user_data['id']})")
            elif response.status_code == 400 and "REGISTER_USER_ALREADY_EXISTS" in response.text:
                print("   ✓ User already exists (expected for repeated tests)")
                # Login to get token
                login_response = await client.post(
                    "/api/auth/jwt/login",
                    data={
                        "username": register_data["email"],
                        "password": register_data["password"]
                    }
                )
                if login_response.status_code != 200:
                    print(f"   ✗ Login failed: {login_response.status_code}")
                    return False
            else:
                print(f"   ✗ Registration failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Registration error: {e}")
            return False
        
        print()
        
        # Test 2: Login and get token
        print("3. Testing user login...")
        try:
            response = await client.post(
                "/api/auth/jwt/login",
                data={
                    "username": register_data["email"],
                    "password": register_data["password"]
                }
            )
            
            if response.status_code == 200:
                token_data = response.json()
                token = token_data["access_token"]
                print("   ✓ Login successful, token received")
            else:
                print(f"   ✗ Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Login error: {e}")
            return False
        
        print()
        
        # Set authorization header for subsequent requests
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test 3: Get current user profile
        print("4. Testing GET /api/users/me...")
        try:
            response = await client.get("/api/users/me", headers=headers)
            
            if response.status_code == 200:
                user = response.json()
                print(f"   ✓ Profile retrieved successfully")
                print(f"     - Email: {user['email']}")
                print(f"     - Breedery Name: {user.get('breedery_name', 'Not set')}")
                print(f"     - Profile Image: {user.get('profile_image_path', 'Not set')}")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 4: Update user profile
        print("5. Testing PATCH /api/users/me...")
        try:
            update_data = {
                "breedery_name": "Test Breedery",
                "breedery_description": "A test breeding operation",
                "search_tags": ["golden-retriever", "champion-bloodline"]
            }
            
            response = await client.patch("/api/users/me", json=update_data, headers=headers)
            
            if response.status_code == 200:
                user = response.json()
                print(f"   ✓ Profile updated successfully")
                print(f"     - Breedery Name: {user['breedery_name']}")
                print(f"     - Description: {user['breedery_description'][:50]}...")
                print(f"     - Tags: {user['search_tags']}")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 5: Create a location
        print("6. Testing POST /api/locations...")
        try:
            location_data = {
                "name": "Main Kennel",
                "address1": "123 Dog Street",
                "address2": "Suite 100",
                "city": "Dogville",
                "state": "CA",
                "country": "USA",
                "zipcode": "90210",
                "location_type": "user"
            }
            
            response = await client.post("/api/locations/", json=location_data, headers=headers)
            
            if response.status_code == 201:
                location = response.json()
                location_id = location['id']
                print(f"   ✓ Location created successfully (ID: {location_id})")
                print(f"     - Name: {location['name']}")
                print(f"     - Address: {location['address1']}, {location['city']}")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 6: Get all locations
        print("7. Testing GET /api/locations...")
        try:
            response = await client.get("/api/locations/", headers=headers)
            
            if response.status_code == 200:
                locations = response.json()
                print(f"   ✓ Locations retrieved successfully")
                print(f"     - Total locations: {len(locations)}")
                for loc in locations[:3]:  # Show first 3
                    print(f"     - {loc['name']} ({loc['city']}, {loc['state']})")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 7: Update location
        print("8. Testing PUT /api/locations/{id}...")
        try:
            update_data = {
                "name": "Updated Main Kennel",
                "address1": "456 Dog Avenue"
            }
            
            response = await client.put(
                f"/api/locations/{location_id}",
                json=update_data,
                headers=headers
            )
            
            if response.status_code == 200:
                location = response.json()
                print(f"   ✓ Location updated successfully")
                print(f"     - New Name: {location['name']}")
                print(f"     - New Address: {location['address1']}")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 8: Verify authentication is required
        print("9. Testing authentication requirement...")
        try:
            response = await client.get("/api/users/me")  # No auth header
            
            if response.status_code == 401:
                print("   ✓ Unauthenticated request correctly rejected")
            else:
                print(f"   ✗ Expected 401, got {response.status_code}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
        
        print()
        
        # Test 9: Delete location
        print("10. Testing DELETE /api/locations/{id}...")
        try:
            response = await client.delete(
                f"/api/locations/{location_id}",
                headers=headers
            )
            
            if response.status_code == 204:
                print("   ✓ Location deleted successfully")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
    
    print()
    print("=" * 80)
    print("All API endpoint tests passed! ✓")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    result = asyncio.run(test_endpoints())
    sys.exit(0 if result else 1)
