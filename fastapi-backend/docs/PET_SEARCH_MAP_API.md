# Pet Search with Map - API Documentation

## Overview

The Pet Search with Map feature provides location-based search capabilities for discovering pets and breeders. This API enables users to search for breeding locations within a specified radius, filter by breed, and access geocoding services.

## Base URL

```
http://localhost:8000/api
```

Production: `https://api.yourdomain.com/api`

## Authentication

Most endpoints require JWT authentication. Include the token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

**Note:** Search endpoints are publicly accessible (no authentication required) to allow guest users to search for pets.

---

## Endpoints

### 1. Search Breeders by Location

Search for breeding locations within a specified radius of a geographic point.

**Endpoint:** `GET /api/search/breeders`

**Authentication:** Not required (public endpoint)

**Query Parameters:**

| Parameter | Type | Required | Description | Constraints |
|-----------|------|----------|-------------|-------------|
| `latitude` | float | Yes | Search center latitude | -90 to 90 |
| `longitude` | float | Yes | Search center longitude | -180 to 180 |
| `radius` | float | Yes | Search radius in miles | 1 to 100 |
| `breed_id` | integer | No | Filter by specific breed | Valid breed ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40&breed_id=123"
```

**Example Response:**

```json
[
  {
    "location_id": 456,
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "breeder_name": "Happy Paws Kennel",
    "latitude": 40.7580,
    "longitude": -73.9855,
    "distance": 5.2,
    "available_breeds": [
      {
        "breed_id": 123,
        "breed_name": "Golden Retriever",
        "pet_count": 3
      },
      {
        "breed_id": 124,
        "breed_name": "Labrador Retriever",
        "pet_count": 2
      }
    ],
    "thumbnail_url": "/storage/profile_550e8400_thumb.jpg",
    "location_description": "Professional breeding facility in Manhattan",
    "rating": 4.8
  },
  {
    "location_id": 789,
    "user_id": "660e8400-e29b-41d4-a716-446655440001",
    "breeder_name": "Sunshine Breeders",
    "latitude": 40.6782,
    "longitude": -73.9442,
    "distance": 12.7,
    "available_breeds": [
      {
        "breed_id": 123,
        "breed_name": "Golden Retriever",
        "pet_count": 5
      }
    ],
    "thumbnail_url": "/storage/profile_660e8400_thumb.jpg",
    "location_description": "Family-owned breeding operation in Brooklyn",
    "rating": 4.9
  }
]
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `location_id` | integer | Unique location identifier |
| `user_id` | UUID | Breeder's user ID |
| `breeder_name` | string | Breeder's business name |
| `latitude` | float | Location latitude |
| `longitude` | float | Location longitude |
| `distance` | float | Distance from search center in miles (1 decimal) |
| `available_breeds` | array | List of breeds available at this location |
| `available_breeds[].breed_id` | integer | Breed identifier |
| `available_breeds[].breed_name` | string | Breed name |
| `available_breeds[].pet_count` | integer | Number of pets of this breed |
| `thumbnail_url` | string | URL to breeder's profile image |
| `location_description` | string | Location description |
| `rating` | float | Breeder rating (if available) |

**Error Responses:**

```json
// 400 Bad Request - Invalid parameters
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid latitude value",
    "details": {
      "field": "latitude",
      "value": 95.0,
      "constraint": "Must be between -90 and 90"
    }
  }
}

// 500 Internal Server Error - Database error
{
  "error": {
    "code": "DATABASE_ERROR",
    "message": "Failed to execute geospatial query",
    "details": {
      "hint": "Ensure PostGIS extension is enabled"
    }
  }
}
```

**Performance Notes:**
- Uses PostGIS spatial indexing for efficient queries
- Average response time: < 200ms for 100 results
- Results are sorted by distance (nearest first)
- Maximum 1000 results returned per request

---

### 2. Breed Autocomplete

Search for breeds by partial name match for autocomplete functionality.

**Endpoint:** `GET /api/breeds/autocomplete`

**Authentication:** Not required (public endpoint)

**Query Parameters:**

| Parameter | Type | Required | Description | Constraints |
|-----------|------|----------|-------------|-------------|
| `search_term` | string | Yes | Partial breed name | 2-100 characters |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/breeds/autocomplete?search_term=gold"
```

**Example Response:**

```json
[
  {
    "id": 123,
    "name": "Golden Retriever",
    "code": "GR"
  },
  {
    "id": 456,
    "name": "Golden Doodle",
    "code": "GD"
  }
]
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Breed identifier |
| `name` | string | Full breed name |
| `code` | string | Breed code (optional) |

**Error Responses:**

```json
// 400 Bad Request - Search term too short
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Search term must be at least 2 characters",
    "details": {
      "field": "search_term",
      "value": "g",
      "min_length": 2
    }
  }
}
```

**Performance Notes:**
- Uses database ILIKE for case-insensitive partial matching
- Results limited to 10 matches
- Average response time: < 50ms
- Results ordered by relevance (exact matches first)

---

### 3. Geocode ZIP Code

Convert a US ZIP code to geographic coordinates.

**Endpoint:** `GET /api/geocode/zip`

**Authentication:** Not required (public endpoint)

**Query Parameters:**

| Parameter | Type | Required | Description | Constraints |
|-----------|------|----------|-------------|-------------|
| `zip` | string | Yes | US ZIP code | 5-digit numeric string |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/geocode/zip?zip=10001"
```

**Example Response:**

```json
{
  "latitude": 40.7506,
  "longitude": -73.9971
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `latitude` | float | Latitude coordinate |
| `longitude` | float | Longitude coordinate |

**Error Responses:**

```json
// 400 Bad Request - Invalid ZIP format
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid ZIP code format",
    "details": {
      "field": "zip",
      "value": "abc12",
      "expected": "5-digit numeric string"
    }
  }
}

// 404 Not Found - ZIP code not found
{
  "error": {
    "code": "NOT_FOUND",
    "message": "ZIP code not found",
    "details": {
      "zip": "99999"
    }
  }
}

// 429 Too Many Requests - Rate limit exceeded
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Geocoding rate limit exceeded",
    "details": {
      "retry_after": 1.0
    }
  }
}

// 503 Service Unavailable - Nominatim unavailable
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "Geocoding service temporarily unavailable",
    "details": {
      "service": "Nominatim",
      "retry_after": 60
    }
  }
}
```

**Caching:**
- Results cached for 24 hours (86400 seconds)
- Cache key: `geocode:zip:{zip_code}`
- Subsequent requests return cached results instantly

**Rate Limiting:**
- External API: 1 request per second (Nominatim policy)
- Cached requests: No rate limit
- Rate limit applies per server instance

**Performance Notes:**
- Cache hit: < 10ms response time
- Cache miss: 500-2000ms (external API call)
- Cache hit rate typically > 90% in production

---

### 4. Reverse Geocode

Convert geographic coordinates to an address.

**Endpoint:** `GET /api/geocode/reverse`

**Authentication:** Not required (public endpoint)

**Query Parameters:**

| Parameter | Type | Required | Description | Constraints |
|-----------|------|----------|-------------|-------------|
| `lat` | float | Yes | Latitude | -90 to 90 |
| `lon` | float | Yes | Longitude | -180 to 180 |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/geocode/reverse?lat=40.7506&lon=-73.9971"
```

**Example Response:**

```json
{
  "zip_code": "10001",
  "city": "New York",
  "state": "New York",
  "country": "United States"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `zip_code` | string | Postal code (may be null) |
| `city` | string | City name (may be null) |
| `state` | string | State/province name (may be null) |
| `country` | string | Country name (may be null) |

**Error Responses:**

```json
// 400 Bad Request - Invalid coordinates
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid latitude value",
    "details": {
      "field": "lat",
      "value": 95.0,
      "constraint": "Must be between -90 and 90"
    }
  }
}

// 404 Not Found - No address found
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No address found for coordinates",
    "details": {
      "latitude": 0.0,
      "longitude": 0.0
    }
  }
}
```

**Caching:**
- Results cached for 24 hours
- Cache key: `geocode:reverse:{latitude}:{longitude}`

**Rate Limiting:**
- Same as forward geocoding (1 req/sec to Nominatim)

**Performance Notes:**
- Cache hit: < 10ms
- Cache miss: 500-2000ms
- Coordinates rounded to 4 decimal places for caching (~11m precision)

---

## Data Models

### BreederSearchResult

```typescript
interface BreederSearchResult {
  location_id: number;
  user_id: string;  // UUID
  breeder_name: string;
  latitude: number;
  longitude: number;
  distance: number;  // miles, 1 decimal place
  available_breeds: BreedInfo[];
  thumbnail_url: string | null;
  location_description: string | null;
  rating: number | null;
}
```

### BreedInfo

```typescript
interface BreedInfo {
  breed_id: number;
  breed_name: string;
  pet_count: number;
}
```

### Coordinates

```typescript
interface Coordinates {
  latitude: number;
  longitude: number;
}
```

### Address

```typescript
interface Address {
  zip_code: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
}
```

### BreedAutocomplete

```typescript
interface BreedAutocomplete {
  id: number;
  name: string;
  code: string | null;
}
```

---

## Usage Examples

### JavaScript/TypeScript (Axios)

```typescript
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

// Search for breeders
async function searchBreeders(
  latitude: number,
  longitude: number,
  radius: number,
  breedId?: number
) {
  const params: any = { latitude, longitude, radius };
  if (breedId) params.breed_id = breedId;
  
  const response = await axios.get(`${API_BASE_URL}/search/breeders`, {
    params
  });
  
  return response.data;
}

// Breed autocomplete
async function searchBreeds(searchTerm: string) {
  const response = await axios.get(`${API_BASE_URL}/breeds/autocomplete`, {
    params: { search_term: searchTerm }
  });
  
  return response.data;
}

// Geocode ZIP code
async function geocodeZip(zip: string) {
  const response = await axios.get(`${API_BASE_URL}/geocode/zip`, {
    params: { zip }
  });
  
  return response.data;
}

// Reverse geocode
async function reverseGeocode(lat: number, lon: number) {
  const response = await axios.get(`${API_BASE_URL}/geocode/reverse`, {
    params: { lat, lon }
  });
  
  return response.data;
}

// Example usage
async function findNearbyGoldenRetrievers() {
  try {
    // Get coordinates from ZIP
    const coords = await geocodeZip('10001');
    
    // Search for Golden Retrievers within 40 miles
    const breeders = await searchBreeders(
      coords.latitude,
      coords.longitude,
      40,
      123  // Golden Retriever breed ID
    );
    
    console.log(`Found ${breeders.length} breeders`);
    breeders.forEach(breeder => {
      console.log(`${breeder.breeder_name} - ${breeder.distance} miles away`);
    });
  } catch (error) {
    console.error('Search failed:', error);
  }
}
```

### Python (httpx)

```python
import httpx
from typing import Optional, List, Dict

API_BASE_URL = "http://localhost:8000/api"

async def search_breeders(
    latitude: float,
    longitude: float,
    radius: float,
    breed_id: Optional[int] = None
) -> List[Dict]:
    """Search for breeders within radius."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius
    }
    if breed_id:
        params["breed_id"] = breed_id
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/search/breeders",
            params=params
        )
        response.raise_for_status()
        return response.json()

async def search_breeds(search_term: str) -> List[Dict]:
    """Search breeds by partial name."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/breeds/autocomplete",
            params={"search_term": search_term}
        )
        response.raise_for_status()
        return response.json()

async def geocode_zip(zip_code: str) -> Dict:
    """Convert ZIP code to coordinates."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/geocode/zip",
            params={"zip": zip_code}
        )
        response.raise_for_status()
        return response.json()

# Example usage
async def find_nearby_golden_retrievers():
    try:
        # Get coordinates from ZIP
        coords = await geocode_zip("10001")
        
        # Search for Golden Retrievers within 40 miles
        breeders = await search_breeders(
            latitude=coords["latitude"],
            longitude=coords["longitude"],
            radius=40,
            breed_id=123  # Golden Retriever
        )
        
        print(f"Found {len(breeders)} breeders")
        for breeder in breeders:
            print(f"{breeder['breeder_name']} - {breeder['distance']} miles away")
    except httpx.HTTPError as e:
        print(f"Search failed: {e}")
```

### cURL Examples

```bash
# Search for all breeders within 40 miles of NYC
curl -X GET "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"

# Search for Golden Retrievers only
curl -X GET "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40&breed_id=123"

# Breed autocomplete
curl -X GET "http://localhost:8000/api/breeds/autocomplete?search_term=gold"

# Geocode ZIP code
curl -X GET "http://localhost:8000/api/geocode/zip?zip=10001"

# Reverse geocode
curl -X GET "http://localhost:8000/api/geocode/reverse?lat=40.7506&lon=-73.9971"
```

---

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      // Additional context-specific information
    }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable |
| `DATABASE_ERROR` | 500 | Database query failed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Retry Strategy

For transient errors (429, 503), implement exponential backoff:

```typescript
async function fetchWithRetry(
  url: string,
  maxRetries: number = 3
): Promise<any> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await axios.get(url);
      return response.data;
    } catch (error) {
      if (error.response?.status === 429 || error.response?.status === 503) {
        const delay = Math.pow(2, i) * 1000;  // 1s, 2s, 4s
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
      throw error;
    }
  }
  throw new Error('Max retries exceeded');
}
```

---

## Performance Considerations

### Caching Strategy

1. **Geocoding Results**: Cached for 24 hours
   - Reduces external API calls by ~90%
   - Improves response time from 1-2s to <10ms

2. **Breed Autocomplete**: Consider client-side caching
   - Cache breed list on first load
   - Filter locally for instant results

3. **Search Results**: Consider short-term caching (5-10 minutes)
   - Reduces database load for popular searches
   - Balance freshness vs performance

### Query Optimization

1. **Spatial Indexing**: PostGIS GIST index on coordinates
   - Enables efficient radius queries
   - Sub-100ms query times for 10,000+ locations

2. **Breed Filtering**: Indexed foreign keys
   - Fast JOIN operations
   - Efficient breed_id filtering

3. **Result Limiting**: Paginate large result sets
   - Consider adding `limit` and `offset` parameters
   - Default limit: 100 results

### Rate Limiting

**Nominatim Policy:**
- Maximum 1 request per second
- User-Agent header required
- Bulk geocoding discouraged

**Implementation:**
- Rate limiter enforces 1 req/sec
- Queue requests during bursts
- Cache aggressively to minimize external calls

---

## Testing

### Test Endpoints

Use the following test data for development:

```bash
# Test ZIP codes
10001  # Manhattan, NY
90210  # Beverly Hills, CA
60601  # Chicago, IL

# Test coordinates
40.7128, -74.0060  # New York City
34.0522, -118.2437  # Los Angeles
41.8781, -87.6298  # Chicago

# Test breed IDs (adjust based on your database)
123  # Golden Retriever
124  # Labrador Retriever
125  # German Shepherd
```

### Integration Tests

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_breeder_search(client: AsyncClient):
    """Test breeder search endpoint."""
    response = await client.get(
        "/api/search/breeders",
        params={
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 40
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "location_id" in data[0]
        assert "distance" in data[0]
        assert data[0]["distance"] <= 40

@pytest.mark.asyncio
async def test_breed_autocomplete(client: AsyncClient):
    """Test breed autocomplete endpoint."""
    response = await client.get(
        "/api/breeds/autocomplete",
        params={"search_term": "gold"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10
```

---

## Changelog

### Version 1.0.0 (January 2026)

**Initial Release:**
- Breeder search by location and radius
- Breed autocomplete
- ZIP code geocoding
- Reverse geocoding
- PostGIS spatial queries
- Redis caching for geocoding
- Rate limiting for external APIs

---

## Support

For API issues or questions:

1. Check this documentation
2. Review error messages and codes
3. Check server logs for detailed errors
4. Contact development team

## Related Documentation

- [Main README](../README.md)
- [Geocoding Service Documentation](GEOCODING_SERVICE.md)
- [Deployment Guide](DEPLOYMENT.md)
- [PostGIS Setup](../POSTGIS_SETUP_SUMMARY.md)
