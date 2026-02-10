# Geocoding Service Documentation

## Overview

The Geocoding Service provides address-to-coordinate (forward geocoding) and coordinate-to-address (reverse geocoding) conversion using OpenStreetMap's Nominatim service. The service includes built-in caching, rate limiting, and error handling to ensure reliable operation.

## Features

- **Forward Geocoding**: Convert ZIP codes to coordinates
- **Reverse Geocoding**: Convert coordinates to addresses
- **Caching**: 24-hour Redis cache to reduce external API calls
- **Rate Limiting**: Automatic 1 req/sec throttling (Nominatim policy)
- **Error Handling**: Graceful fallbacks and retry logic
- **Free Service**: No API keys or billing required

## Architecture

```
┌─────────────────┐
│   Application   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GeocodingService│
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌──────────┐
│ Redis │ │Nominatim │
│ Cache │ │   API    │
└───────┘ └──────────┘
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Redis Configuration (required for caching)
REDIS_URL=redis://localhost:6379/0

# Nominatim Configuration
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=86400
```

### Configuration Details

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` | Yes |
| `NOMINATIM_URL` | Nominatim API base URL | `https://nominatim.openstreetmap.org` | Yes |
| `GEOCODING_USER_AGENT` | User-Agent header for Nominatim | `BreedyPetSearch/1.0` | Yes |
| `GEOCODING_RATE_LIMIT` | Requests per second limit | `1.0` | Yes |
| `GEOCODING_CACHE_TTL` | Cache TTL in seconds | `86400` (24 hours) | Yes |

**Important Notes:**

1. **User-Agent Required**: Nominatim requires a valid User-Agent header. Use your application name and version.

2. **Rate Limit**: Nominatim's usage policy requires max 1 request per second. Do not increase this value.

3. **Redis Required**: The service requires Redis for caching. Without Redis, every request will hit Nominatim, likely exceeding rate limits.

4. **Cache TTL**: 24 hours is recommended. ZIP codes and addresses rarely change, so longer caching is safe.

## Usage

### Service Initialization

The service is automatically initialized and injected via FastAPI dependencies:

```python
from app.services.geocoding_service import GeocodingService
from app.dependencies import get_redis

# In your router
@router.get("/geocode/zip")
async def geocode_zip(
    zip: str,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    cache: Redis = Depends(get_redis)
):
    return await geocoding_service.geocode_zip(zip, cache)
```

### Forward Geocoding (ZIP to Coordinates)

Convert a US ZIP code to latitude/longitude coordinates:

```python
from app.services.geocoding_service import GeocodingService

async def example_forward_geocoding():
    service = GeocodingService()
    
    # Geocode a ZIP code
    result = await service.geocode_zip("10001", redis_client)
    
    print(f"Latitude: {result.latitude}")
    print(f"Longitude: {result.longitude}")
    # Output:
    # Latitude: 40.7506
    # Longitude: -73.9971
```

**Parameters:**
- `zip_code` (str): 5-digit US ZIP code
- `cache` (Redis): Redis client for caching

**Returns:**
- `Coordinates` object with `latitude` and `longitude` fields

**Raises:**
- `HTTPException(404)`: ZIP code not found
- `HTTPException(429)`: Rate limit exceeded
- `HTTPException(503)`: Nominatim service unavailable

### Reverse Geocoding (Coordinates to Address)

Convert latitude/longitude coordinates to an address:

```python
async def example_reverse_geocoding():
    service = GeocodingService()
    
    # Reverse geocode coordinates
    result = await service.reverse_geocode(40.7506, -73.9971, redis_client)
    
    print(f"ZIP: {result.zip_code}")
    print(f"City: {result.city}")
    print(f"State: {result.state}")
    print(f"Country: {result.country}")
    # Output:
    # ZIP: 10001
    # City: New York
    # State: New York
    # Country: United States
```

**Parameters:**
- `latitude` (float): Latitude coordinate (-90 to 90)
- `longitude` (float): Longitude coordinate (-180 to 180)
- `cache` (Redis): Redis client for caching

**Returns:**
- `Address` object with `zip_code`, `city`, `state`, and `country` fields (all optional)

**Raises:**
- `HTTPException(404)`: No address found for coordinates
- `HTTPException(429)`: Rate limit exceeded
- `HTTPException(503)`: Nominatim service unavailable

## Caching Strategy

### Cache Keys

The service uses the following cache key patterns:

```python
# Forward geocoding
f"geocode:zip:{zip_code}"
# Example: "geocode:zip:10001"

# Reverse geocoding
f"geocode:reverse:{latitude}:{longitude}"
# Example: "geocode:reverse:40.7506:-73.9971"
```

### Cache Behavior

1. **Cache Hit**: Returns cached result immediately (<10ms)
2. **Cache Miss**: 
   - Applies rate limiting
   - Calls Nominatim API (500-2000ms)
   - Stores result in cache
   - Returns result

### Cache TTL

- Default: 24 hours (86400 seconds)
- Configurable via `GEOCODING_CACHE_TTL` environment variable
- Recommended: 24-72 hours (addresses rarely change)

### Cache Invalidation

Caches automatically expire after TTL. Manual invalidation:

```python
# Invalidate specific ZIP code
await redis_client.delete("geocode:zip:10001")

# Invalidate specific coordinates
await redis_client.delete("geocode:reverse:40.7506:-73.9971")

# Clear all geocoding caches
keys = await redis_client.keys("geocode:*")
if keys:
    await redis_client.delete(*keys)
```

## Rate Limiting

### Nominatim Usage Policy

From [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/):

> An absolute maximum of 1 request per second

### Implementation

The service uses `aiolimiter` to enforce rate limiting:

```python
from aiolimiter import AsyncLimiter

# 1 request per 1 second
rate_limiter = AsyncLimiter(1, 1)

async def call_nominatim():
    async with rate_limiter:
        # API call here
        pass
```

### Rate Limit Behavior

1. **Within Limit**: Request proceeds immediately
2. **Exceeds Limit**: Request waits until rate limit allows
3. **Cached Request**: No rate limiting applied (instant response)

### Monitoring Rate Limits

```python
# Check current rate limit state
print(f"Available capacity: {rate_limiter.available_capacity}")
print(f"Max capacity: {rate_limiter.max_capacity}")
```

## Error Handling

### Error Types

#### 1. ZIP Code Not Found (404)

```python
try:
    result = await service.geocode_zip("99999", cache)
except HTTPException as e:
    if e.status_code == 404:
        print("ZIP code not found")
        # Fallback: prompt user for manual entry
```

**Causes:**
- Invalid ZIP code
- ZIP code not in Nominatim database
- Non-US ZIP code

**Resolution:**
- Validate ZIP code format before calling
- Provide manual coordinate entry option
- Show user-friendly error message

#### 2. Rate Limit Exceeded (429)

```python
try:
    result = await service.geocode_zip("10001", cache)
except HTTPException as e:
    if e.status_code == 429:
        retry_after = e.detail.get("retry_after", 1.0)
        print(f"Rate limited. Retry after {retry_after}s")
        # Implement exponential backoff
```

**Causes:**
- Too many requests in short time
- Multiple server instances without shared rate limiter
- Cache failure causing all requests to hit API

**Resolution:**
- Ensure Redis caching is working
- Implement request queuing
- Use exponential backoff for retries

#### 3. Service Unavailable (503)

```python
try:
    result = await service.geocode_zip("10001", cache)
except HTTPException as e:
    if e.status_code == 503:
        print("Geocoding service unavailable")
        # Fallback: use cached data or manual entry
```

**Causes:**
- Nominatim server down
- Network connectivity issues
- Nominatim blocking requests (policy violation)

**Resolution:**
- Check Nominatim status: https://status.openstreetmap.org/
- Verify User-Agent header is set correctly
- Implement fallback to cached data
- Provide manual coordinate entry

### Retry Strategy

Implement exponential backoff for transient errors:

```python
async def geocode_with_retry(
    service: GeocodingService,
    zip_code: str,
    cache: Redis,
    max_retries: int = 3
):
    for attempt in range(max_retries):
        try:
            return await service.geocode_zip(zip_code, cache)
        except HTTPException as e:
            if e.status_code in [429, 503] and attempt < max_retries - 1:
                delay = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(delay)
                continue
            raise
```

## Performance

### Benchmarks

| Scenario | Response Time | Notes |
|----------|---------------|-------|
| Cache Hit | < 10ms | Redis lookup |
| Cache Miss (Nominatim) | 500-2000ms | External API call |
| Rate Limited | 1000ms+ | Waiting for rate limit |
| Service Unavailable | 5000ms+ | Timeout |

### Optimization Tips

1. **Maximize Cache Hits**:
   - Use longer TTL (24-72 hours)
   - Pre-populate cache with common ZIP codes
   - Round coordinates to reduce cache misses

2. **Batch Geocoding**:
   - Geocode during off-peak hours
   - Queue requests to respect rate limits
   - Use background tasks for non-urgent geocoding

3. **Fallback Strategies**:
   - Keep stale cache data as fallback
   - Provide manual coordinate entry
   - Use approximate coordinates for common areas

### Cache Hit Rate

Monitor cache effectiveness:

```python
# Track cache hits/misses
cache_hits = 0
cache_misses = 0

async def geocode_with_metrics(zip_code: str):
    global cache_hits, cache_misses
    
    cache_key = f"geocode:zip:{zip_code}"
    cached = await redis_client.get(cache_key)
    
    if cached:
        cache_hits += 1
    else:
        cache_misses += 1
    
    # Calculate hit rate
    total = cache_hits + cache_misses
    hit_rate = (cache_hits / total) * 100 if total > 0 else 0
    print(f"Cache hit rate: {hit_rate:.1f}%")
```

**Target Metrics:**
- Cache hit rate: > 90%
- Average response time: < 100ms
- P95 response time: < 500ms

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_geocode_zip_cache_hit(redis_mock):
    """Test geocoding with cache hit."""
    service = GeocodingService()
    
    # Mock cache hit
    redis_mock.get.return_value = '{"latitude": 40.7506, "longitude": -73.9971}'
    
    result = await service.geocode_zip("10001", redis_mock)
    
    assert result.latitude == 40.7506
    assert result.longitude == -73.9971
    redis_mock.get.assert_called_once()

@pytest.mark.asyncio
async def test_geocode_zip_cache_miss(redis_mock, httpx_mock):
    """Test geocoding with cache miss."""
    service = GeocodingService()
    
    # Mock cache miss
    redis_mock.get.return_value = None
    
    # Mock Nominatim response
    httpx_mock.get.return_value = AsyncMock(
        status_code=200,
        json=lambda: [{"lat": "40.7506", "lon": "-73.9971"}]
    )
    
    result = await service.geocode_zip("10001", redis_mock)
    
    assert result.latitude == 40.7506
    redis_mock.setex.assert_called_once()

@pytest.mark.asyncio
async def test_geocode_zip_not_found(redis_mock, httpx_mock):
    """Test geocoding with ZIP not found."""
    service = GeocodingService()
    
    redis_mock.get.return_value = None
    httpx_mock.get.return_value = AsyncMock(
        status_code=200,
        json=lambda: []
    )
    
    with pytest.raises(HTTPException) as exc:
        await service.geocode_zip("99999", redis_mock)
    
    assert exc.value.status_code == 404
```

### Integration Tests

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_geocode_zip_integration(redis_client):
    """Test actual geocoding with real Nominatim."""
    service = GeocodingService()
    
    # Test with real ZIP code
    result = await service.geocode_zip("10001", redis_client)
    
    # Verify coordinates are in NYC area
    assert 40.7 < result.latitude < 40.8
    assert -74.1 < result.longitude < -73.9
    
    # Verify caching
    cached = await redis_client.get("geocode:zip:10001")
    assert cached is not None
```

### Load Testing

Test rate limiting and caching under load:

```python
import asyncio

async def load_test_geocoding():
    """Test geocoding under load."""
    service = GeocodingService()
    
    # Generate 100 requests
    tasks = [
        service.geocode_zip(f"1000{i % 10}", redis_client)
        for i in range(100)
    ]
    
    start = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start
    
    # Analyze results
    successes = sum(1 for r in results if not isinstance(r, Exception))
    failures = len(results) - successes
    
    print(f"Duration: {duration:.2f}s")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"Requests/sec: {len(results) / duration:.2f}")
```

## Troubleshooting

### Common Issues

#### Issue: All requests return 503

**Symptoms:**
- Every geocoding request fails with 503
- Error: "Geocoding service temporarily unavailable"

**Diagnosis:**
```bash
# Test Nominatim directly
curl "https://nominatim.openstreetmap.org/search?postalcode=10001&country=US&format=json"

# Check User-Agent
curl -H "User-Agent: BreedyPetSearch/1.0" \
  "https://nominatim.openstreetmap.org/search?postalcode=10001&country=US&format=json"
```

**Solutions:**
1. Verify `GEOCODING_USER_AGENT` is set in .env
2. Check Nominatim status: https://status.openstreetmap.org/
3. Verify network connectivity
4. Check if IP is blocked (excessive requests)

#### Issue: Rate limit errors despite caching

**Symptoms:**
- Frequent 429 errors
- Cache hit rate < 50%

**Diagnosis:**
```bash
# Check Redis connectivity
redis-cli ping

# Check cache keys
redis-cli keys "geocode:*"

# Check cache TTL
redis-cli ttl "geocode:zip:10001"
```

**Solutions:**
1. Verify Redis is running and accessible
2. Check `REDIS_URL` in .env
3. Increase `GEOCODING_CACHE_TTL`
4. Pre-populate cache with common ZIP codes

#### Issue: Slow response times

**Symptoms:**
- Response times > 2 seconds
- Inconsistent performance

**Diagnosis:**
```python
# Add timing logs
import time

start = time.time()
result = await service.geocode_zip("10001", cache)
duration = time.time() - start
print(f"Geocoding took {duration:.3f}s")
```

**Solutions:**
1. Check cache hit rate (should be > 90%)
2. Verify Redis performance
3. Check network latency to Nominatim
4. Consider using a local Nominatim instance

### Debug Mode

Enable debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app.services.geocoding_service")
```

This will log:
- Cache hits/misses
- Nominatim API calls
- Rate limiting events
- Error details

## Alternative Services

If Nominatim is unavailable or insufficient, consider these alternatives:

### 1. Photon (OpenStreetMap)

```bash
NOMINATIM_URL=https://photon.komoot.io
```

**Pros:**
- Based on OpenStreetMap data
- No rate limits
- Fast response times

**Cons:**
- Different API format (requires code changes)
- Less accurate for US ZIP codes

### 2. Local Nominatim Instance

Run your own Nominatim server:

```bash
# Docker setup
docker run -d \
  -p 8080:8080 \
  -e PBF_URL=https://download.geofabrik.de/north-america/us-latest.osm.pbf \
  mediagis/nominatim:latest

# Update configuration
NOMINATIM_URL=http://localhost:8080
GEOCODING_RATE_LIMIT=10.0  # Can increase with local instance
```

**Pros:**
- No rate limits
- Full control
- Better performance

**Cons:**
- Requires infrastructure
- Needs regular updates
- Storage requirements (50GB+ for US data)

### 3. Commercial Services

For production with high volume, consider:

- **Google Geocoding API**: Most accurate, requires API key and billing
- **Mapbox Geocoding**: Good accuracy, generous free tier
- **HERE Geocoding**: Enterprise-grade, requires account

## Best Practices

1. **Always Use Caching**: Never call Nominatim without caching
2. **Respect Rate Limits**: Never exceed 1 req/sec to public Nominatim
3. **Set User-Agent**: Always include your application name
4. **Handle Errors Gracefully**: Provide fallbacks for all error cases
5. **Monitor Performance**: Track cache hit rate and response times
6. **Pre-populate Cache**: Cache common ZIP codes during deployment
7. **Use Exponential Backoff**: Retry transient errors with delays
8. **Validate Input**: Check ZIP format before calling service
9. **Log Errors**: Log all geocoding failures for debugging
10. **Test Thoroughly**: Include integration tests with real API

## Security Considerations

1. **Rate Limiting**: Prevents abuse and API blocking
2. **Input Validation**: Prevents injection attacks
3. **Error Messages**: Don't expose internal details to users
4. **API Keys**: Not required for Nominatim (public service)
5. **HTTPS**: Always use HTTPS for Nominatim calls
6. **User-Agent**: Identifies your application for abuse tracking

## Support

For issues with the Geocoding Service:

1. Check this documentation
2. Review error logs
3. Test Nominatim directly
4. Check OpenStreetMap status
5. Contact development team

## Related Documentation

- [Pet Search Map API Documentation](PET_SEARCH_MAP_API.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Main README](../README.md)
- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
