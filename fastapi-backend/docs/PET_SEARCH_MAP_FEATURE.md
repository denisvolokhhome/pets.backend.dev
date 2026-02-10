# Pet Search with Map - Feature Overview

## Introduction

The Pet Search with Map feature enables users to discover pets and breeders near their location using an interactive map interface. Built with modern geospatial technologies, it provides a seamless search experience similar to popular property and accommodation search platforms.

## Key Features

### For Users

- **Location-Based Search**: Find breeders within a customizable radius (10-100 miles)
- **Breed Filtering**: Search for specific dog breeds with autocomplete
- **Interactive Map**: View breeding locations on an OpenStreetMap-powered map
- **Automatic Location Detection**: Browser geolocation with ZIP code fallback
- **Mobile-Friendly**: Responsive design optimized for mobile devices
- **Public Access**: No authentication required for searching

### For Developers

- **PostGIS Integration**: Efficient geospatial queries with spatial indexing
- **Geocoding Service**: ZIP code to coordinates conversion with caching
- **Rate Limiting**: Automatic throttling to respect API usage policies
- **Caching Strategy**: Redis-based caching for 90%+ cache hit rate
- **Property-Based Testing**: Comprehensive test coverage with Hypothesis
- **RESTful API**: Clean, well-documented API endpoints

## Architecture

### Technology Stack

**Backend:**
- FastAPI (Python async web framework)
- PostgreSQL with PostGIS extension
- Redis (caching)
- SQLAlchemy with GeoAlchemy2
- Nominatim (geocoding)

**Frontend:**
- Angular
- Leaflet.js (map rendering)
- OpenStreetMap (map tiles)
- TypeScript

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Angular Frontend                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Search Page  │  │ Map Component│  │ Breeder Card │      │
│  │  Component   │──│  (Leaflet)   │──│  Component   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────────┬──────────────────────────────────┘
                             │ HTTP/JSON
┌────────────────────────────┼──────────────────────────────────┐
│                   FastAPI Backend                             │
│                    ┌───────▼────────┐                         │
│                    │  Search Router │                         │
│                    └───────┬────────┘                         │
│         ┌──────────────────┼──────────────────┐              │
│         │                  │                  │              │
│  ┌──────▼──────┐  ┌────────▼────────┐  ┌─────▼──────┐      │
│  │   Breeder   │  │     Breed       │  │  Geocoding │      │
│  │   Service   │  │    Service      │  │   Service  │      │
│  └──────┬──────┘  └────────┬────────┘  └─────┬──────┘      │
│         │                  │                  │              │
│  ┌──────▼──────────────────▼──────────────────▼──────┐      │
│  │         PostgreSQL + PostGIS + Redis               │      │
│  └────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │    Nominatim    │
                    │   (Geocoding)   │
                    └─────────────────┘
```

## API Endpoints

### 1. Search Breeders

Find breeding locations within a radius.

```bash
GET /api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40&breed_id=123
```

**Response:**
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
      }
    ],
    "thumbnail_url": "/storage/profile_550e8400_thumb.jpg",
    "location_description": "Professional breeding facility",
    "rating": 4.8
  }
]
```

### 2. Breed Autocomplete

Search breeds for autocomplete.

```bash
GET /api/breeds/autocomplete?search_term=gold
```

**Response:**
```json
[
  {
    "id": 123,
    "name": "Golden Retriever",
    "code": "GR"
  }
]
```

### 3. Geocode ZIP Code

Convert ZIP code to coordinates.

```bash
GET /api/geocode/zip?zip=10001
```

**Response:**
```json
{
  "latitude": 40.7506,
  "longitude": -73.9971
}
```

### 4. Reverse Geocode

Convert coordinates to address.

```bash
GET /api/geocode/reverse?lat=40.7506&lon=-73.9971
```

**Response:**
```json
{
  "zip_code": "10001",
  "city": "New York",
  "state": "New York",
  "country": "United States"
}
```

## Performance

### Benchmarks

| Operation | Response Time | Notes |
|-----------|---------------|-------|
| Breeder Search | < 200ms | With spatial index |
| Breed Autocomplete | < 50ms | Database query |
| Geocoding (cached) | < 10ms | Redis cache hit |
| Geocoding (uncached) | 500-2000ms | External API call |

### Optimization Features

1. **Spatial Indexing**: PostGIS GIST index for sub-100ms queries
2. **Geocoding Cache**: 24-hour Redis cache with 90%+ hit rate
3. **Rate Limiting**: Automatic 1 req/sec throttling for Nominatim
4. **Query Optimization**: Efficient ST_DWithin for radius filtering
5. **Connection Pooling**: Async database connection pool

## Setup Guide

### Prerequisites

1. **PostgreSQL 12+** with PostGIS 3.0+
2. **Redis 6.0+** for caching
3. **Python 3.11+** with Poetry
4. **Node.js 18+** for frontend (if applicable)

### Installation Steps

#### 1. Install PostGIS

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-12-postgis-3

# macOS
brew install postgis

# Enable in database
psql -U postgres -d pet_breeding_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

#### 2. Install Redis

```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis

# Start Redis
redis-server
```

#### 3. Configure Environment

Create `.env` file:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/pet_breeding_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Geocoding
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=86400

# Application
SECRET_KEY=your-secret-key-here
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4200
```

#### 4. Run Migrations

```bash
cd pets.backend.dev/fastapi-backend
poetry install
poetry run alembic upgrade head
```

#### 5. Start Application

```bash
poetry run uvicorn app.main:app --reload
```

#### 6. Verify Installation

```bash
# Test breeder search
curl "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"

# Test geocoding
curl "http://localhost:8000/api/geocode/zip?zip=10001"

# Check API docs
open http://localhost:8000/api/docs
```

## Testing

### Test Suite

The feature includes comprehensive tests:

- **Unit Tests**: Service logic and utilities
- **Integration Tests**: API endpoints and database queries
- **Property-Based Tests**: Universal correctness properties with Hypothesis
- **E2E Tests**: Complete user workflows with Playwright

### Running Tests

```bash
# All tests
poetry run pytest

# Specific test categories
poetry run pytest tests/unit/test_breeder_service.py
poetry run pytest tests/integration/test_search_endpoints.py
poetry run pytest tests/property/test_breeder_search_properties.py

# With coverage
poetry run pytest --cov=app --cov-report=html
```

### Property-Based Tests

The feature includes 41 correctness properties tested with Hypothesis:

- **Property 22**: Haversine distance calculation accuracy
- **Property 23**: Radius filtering correctness
- **Property 24**: Breed filtering completeness
- **Property 26**: Distance-based sorting order
- **Property 36**: Geocoding cache round-trip consistency
- And 36 more...

Each property runs 100+ iterations with randomly generated test data.

## Documentation

### Available Documentation

1. **[API Documentation](PET_SEARCH_MAP_API.md)**: Complete API reference with examples
2. **[Geocoding Service](GEOCODING_SERVICE.md)**: Geocoding service usage and configuration
3. **[Environment Variables](ENVIRONMENT_VARIABLES.md)**: All configuration options
4. **[Deployment Checklist](DEPLOYMENT_CHECKLIST.md)**: Step-by-step deployment guide
5. **[PostGIS Setup](../POSTGIS_SETUP_SUMMARY.md)**: PostGIS installation and configuration

### Quick Links

- **API Docs (Swagger)**: http://localhost:8000/api/docs
- **API Docs (ReDoc)**: http://localhost:8000/api/redoc
- **OpenAPI Spec**: http://localhost:8000/api/openapi.json

## Deployment

### Production Checklist

- [ ] PostGIS extension enabled
- [ ] Redis server running
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] SSL/TLS certificate installed
- [ ] Firewall configured
- [ ] Monitoring and logging set up
- [ ] Backup strategy implemented

See [Deployment Checklist](DEPLOYMENT_CHECKLIST.md) for complete guide.

### Deployment Commands

```bash
# Run migrations
poetry run alembic upgrade head

# Start with multiple workers
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Or with Gunicorn
poetry run gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Monitoring

### Key Metrics

1. **Response Times**:
   - Breeder search: < 200ms (p95)
   - Geocoding (cached): < 10ms
   - Geocoding (uncached): < 2000ms

2. **Cache Performance**:
   - Cache hit rate: > 90%
   - Cache size: Monitor Redis memory usage
   - Cache evictions: Should be minimal

3. **Error Rates**:
   - API errors: < 1%
   - Geocoding failures: < 5%
   - Database errors: < 0.1%

### Monitoring Tools

- **Application**: New Relic, DataDog, Sentry
- **Infrastructure**: Prometheus, Grafana
- **Logs**: ELK Stack, CloudWatch
- **Uptime**: UptimeRobot, Pingdom

## Troubleshooting

### Common Issues

#### PostGIS Not Available

**Symptoms**: Database errors mentioning PostGIS functions

**Solution**:
```bash
psql -U postgres -d pet_breeding_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

#### Redis Connection Failed

**Symptoms**: Geocoding always slow, cache errors

**Solution**:
```bash
# Check Redis
redis-cli ping

# Start if not running
redis-server

# Verify connection
redis-cli -u redis://localhost:6379/0 ping
```

#### Geocoding Rate Limit

**Symptoms**: 429 errors, slow geocoding

**Solution**:
- Verify Redis caching is working
- Check cache hit rate: `redis-cli keys "geocode:*"`
- Ensure `GEOCODING_RATE_LIMIT=1.0` in .env
- Consider local Nominatim instance for high volume

#### Slow Search Queries

**Symptoms**: Breeder search > 500ms

**Solution**:
```sql
-- Verify spatial index exists
SELECT indexname FROM pg_indexes WHERE tablename = 'locations';

-- Recreate if missing
CREATE INDEX idx_locations_coordinates ON locations USING GIST (coordinates);

-- Analyze table
ANALYZE locations;
```

## Best Practices

### Development

1. **Use Local Services**: Run PostgreSQL and Redis locally
2. **Enable Debug Mode**: Set `DEBUG=True` in development
3. **Monitor Logs**: Watch application logs for errors
4. **Test Thoroughly**: Run full test suite before committing
5. **Use Type Hints**: Maintain type safety with mypy

### Production

1. **Disable Debug**: Set `DEBUG=False`
2. **Use Strong Secrets**: Generate secure random keys
3. **Enable HTTPS**: Use SSL/TLS certificates
4. **Monitor Performance**: Track response times and errors
5. **Backup Regularly**: Automated database and Redis backups
6. **Rate Limit**: Protect against abuse
7. **Cache Aggressively**: Maximize geocoding cache hit rate
8. **Scale Horizontally**: Use multiple workers/instances

### Security

1. **Validate Input**: All user input validated
2. **Sanitize Queries**: Use parameterized queries
3. **Limit Access**: Firewall rules for database and Redis
4. **Rotate Secrets**: Regular key rotation
5. **Monitor Abuse**: Track unusual patterns
6. **Update Dependencies**: Regular security updates

## Support

### Getting Help

1. **Documentation**: Check this documentation first
2. **API Docs**: Review Swagger/ReDoc documentation
3. **Logs**: Check application and error logs
4. **Tests**: Run tests to verify functionality
5. **Community**: Search GitHub issues

### Reporting Issues

When reporting issues, include:

- Error messages and stack traces
- Environment details (OS, Python version, etc.)
- Configuration (without secrets)
- Steps to reproduce
- Expected vs actual behavior

### Contact

- **Development Team**: dev@yourdomain.com
- **Operations Team**: ops@yourdomain.com
- **Documentation**: docs@yourdomain.com

## Roadmap

### Planned Features

- [ ] Advanced filtering (price range, availability)
- [ ] Saved searches and alerts
- [ ] Breeder ratings and reviews
- [ ] Direct messaging between users and breeders
- [ ] Photo galleries for breeding locations
- [ ] Mobile app (iOS/Android)
- [ ] Multi-language support
- [ ] Advanced analytics for breeders

### Performance Improvements

- [ ] GraphQL API for flexible queries
- [ ] WebSocket support for real-time updates
- [ ] CDN integration for static assets
- [ ] Database read replicas
- [ ] Advanced caching strategies

## License

Proprietary - Pet Breeding Management System

## Acknowledgments

- **OpenStreetMap**: Free map tiles and data
- **Nominatim**: Free geocoding service
- **PostGIS**: Powerful geospatial extension
- **FastAPI**: Modern Python web framework
- **Leaflet.js**: Interactive map library

---

**Version**: 1.0.0  
**Last Updated**: January 2026  
**Status**: Production Ready

For detailed information, see the complete documentation:
- [API Documentation](PET_SEARCH_MAP_API.md)
- [Geocoding Service](GEOCODING_SERVICE.md)
- [Deployment Guide](DEPLOYMENT_CHECKLIST.md)
- [Environment Variables](ENVIRONMENT_VARIABLES.md)
