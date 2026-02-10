# Environment Variables Documentation

## Overview

This document describes all environment variables used by the Pet Breeding API, including the Pet Search with Map feature. All variables should be defined in a `.env` file in the project root.

## Quick Start

```bash
# Copy the example file
cp .env.example .env

# Edit with your values
nano .env
```

---

## Required Variables

These variables MUST be set for the application to function.

### Database Configuration

#### `DATABASE_URL`

PostgreSQL database connection string with asyncpg driver.

**Format:** `postgresql+asyncpg://user:password@host:port/database`

**Example:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:mypassword@localhost:5432/pet_breeding_db
```

**Notes:**
- Must use `postgresql+asyncpg://` driver for async support
- Ensure PostgreSQL 12+ is installed
- Database must exist before starting application
- User must have CREATE EXTENSION privileges for PostGIS

**Validation:**
```bash
# Test connection
poetry run python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect())"
```

---

### Authentication Configuration

#### `SECRET_KEY`

Secret key for JWT token generation and encryption.

**Format:** String (minimum 32 characters)

**Example:**
```bash
SECRET_KEY=your-secret-key-here-change-in-production
```

**Generation:**
```bash
# Generate a secure random key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Notes:**
- MUST be changed from default in production
- Keep this value secret and secure
- Changing this will invalidate all existing JWT tokens
- Use different keys for development and production

**Security:**
- Minimum 32 characters
- Use cryptographically secure random generation
- Store securely (environment variables, secrets manager)
- Never commit to version control

---

#### `JWT_LIFETIME_SECONDS`

JWT token lifetime in seconds.

**Format:** Integer

**Default:** `3600` (1 hour)

**Example:**
```bash
JWT_LIFETIME_SECONDS=3600
```

**Recommendations:**
- Development: 3600 (1 hour)
- Production: 1800-3600 (30 minutes to 1 hour)
- Mobile apps: 7200-86400 (2 hours to 1 day)

---

### Redis Configuration

#### `REDIS_URL`

Redis connection URL for caching.

**Format:** `redis://[password@]host:port/database`

**Examples:**
```bash
# Without password
REDIS_URL=redis://localhost:6379/0

# With password
REDIS_URL=redis://:mypassword@localhost:6379/0

# Remote Redis
REDIS_URL=redis://:password@redis.example.com:6379/0
```

**Notes:**
- Required for geocoding cache
- Database 0 is recommended for this application
- Ensure Redis 6.0+ is installed and running

**Validation:**
```bash
# Test connection
redis-cli -u redis://localhost:6379/0 ping
# Should return: PONG

# Or with Python
poetry run python -c "import redis; r = redis.from_url('redis://localhost:6379/0'); print(r.ping())"
```

---

### Application Configuration

#### `ALLOWED_ORIGINS`

Comma-separated list of allowed CORS origins.

**Format:** Comma-separated URLs

**Example:**
```bash
# Development
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4200

# Production
ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
```

**Notes:**
- Required for frontend to access API
- Include all frontend URLs (with protocol and port)
- Do not use wildcards (*) in production
- Include both www and non-www versions if applicable

---

## Geocoding Configuration

These variables configure the geocoding service for the Pet Search with Map feature.

### `NOMINATIM_URL`

Base URL for Nominatim geocoding service.

**Format:** URL

**Default:** `https://nominatim.openstreetmap.org`

**Example:**
```bash
# Public Nominatim
NOMINATIM_URL=https://nominatim.openstreetmap.org

# Local Nominatim instance
NOMINATIM_URL=http://localhost:8080

# Alternative service (Photon)
NOMINATIM_URL=https://photon.komoot.io
```

**Notes:**
- Public Nominatim is free but rate-limited
- Consider running local instance for high volume
- See [Geocoding Service Documentation](GEOCODING_SERVICE.md) for alternatives

---

### `GEOCODING_USER_AGENT`

User-Agent header for Nominatim requests.

**Format:** String (application name and version)

**Default:** `BreedyPetSearch/1.0`

**Example:**
```bash
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
```

**Notes:**
- REQUIRED by Nominatim usage policy
- Should identify your application
- Format: `ApplicationName/Version`
- Used for abuse tracking and contact

**Nominatim Policy:**
> Provide a valid HTTP Referer or User-Agent identifying the application

---

### `GEOCODING_RATE_LIMIT`

Maximum requests per second to Nominatim.

**Format:** Float

**Default:** `1.0`

**Example:**
```bash
GEOCODING_RATE_LIMIT=1.0
```

**Notes:**
- MUST be 1.0 or less for public Nominatim
- Nominatim usage policy: "absolute maximum of 1 request per second"
- Can increase for local Nominatim instance
- Violations may result in IP blocking

**DO NOT CHANGE** unless using a local Nominatim instance.

---

### `GEOCODING_CACHE_TTL`

Cache time-to-live for geocoding results in seconds.

**Format:** Integer

**Default:** `86400` (24 hours)

**Example:**
```bash
GEOCODING_CACHE_TTL=86400
```

**Recommendations:**
- Development: 3600 (1 hour)
- Production: 86400-259200 (1-3 days)
- Addresses rarely change, longer TTL is safe

**Notes:**
- Longer TTL reduces external API calls
- Improves response time and reliability
- Reduces load on Nominatim
- ZIP codes and addresses are stable data

---

## Optional Variables

These variables have sensible defaults but can be customized.

### Storage Configuration

#### `STORAGE_PATH`

Directory path for uploaded files.

**Format:** Relative or absolute path

**Default:** `storage/app`

**Example:**
```bash
# Relative path
STORAGE_PATH=storage/app

# Absolute path
STORAGE_PATH=/var/www/pet-breeding/storage
```

**Notes:**
- Directory must be writable by application
- Created automatically if doesn't exist
- Should be outside web root for security

---

#### `STORAGE_URL`

Public URL path for accessing stored files.

**Format:** URL path

**Default:** `/storage`

**Example:**
```bash
STORAGE_URL=/storage
```

**Notes:**
- Used to generate public URLs for images
- Should match web server configuration
- Typically served via symlink or reverse proxy

---

### Application Configuration

#### `APP_NAME`

Application name for display and logging.

**Format:** String

**Default:** `Pet Breeding API`

**Example:**
```bash
APP_NAME=Pet Breeding API
```

---

#### `DEBUG`

Enable debug mode.

**Format:** Boolean (`True` or `False`)

**Default:** `False`

**Example:**
```bash
# Development
DEBUG=True

# Production
DEBUG=False
```

**Notes:**
- MUST be `False` in production
- Enables detailed error messages
- Enables auto-reload in development
- Exposes sensitive information when `True`

---

### Server Configuration

#### `HOST`

Server bind address.

**Format:** IP address

**Default:** `0.0.0.0`

**Example:**
```bash
# Listen on all interfaces
HOST=0.0.0.0

# Listen on localhost only
HOST=127.0.0.1
```

---

#### `PORT`

Server port number.

**Format:** Integer

**Default:** `8000`

**Example:**
```bash
PORT=8000
```

---

### Image Upload Configuration

#### `MAX_IMAGE_SIZE_MB`

Maximum image upload size in megabytes.

**Format:** Integer

**Default:** `10`

**Example:**
```bash
MAX_IMAGE_SIZE_MB=10
```

---

#### `ALLOWED_IMAGE_TYPES`

Comma-separated list of allowed image MIME types.

**Format:** Comma-separated MIME types

**Default:** `image/jpeg,image/png,image/webp`

**Example:**
```bash
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
```

---

#### `IMAGE_MAX_WIDTH`

Maximum image width in pixels.

**Format:** Integer

**Default:** `1920`

**Example:**
```bash
IMAGE_MAX_WIDTH=1920
```

---

#### `IMAGE_MAX_HEIGHT`

Maximum image height in pixels.

**Format:** Integer

**Default:** `1920`

**Example:**
```bash
IMAGE_MAX_HEIGHT=1920
```

---

#### `IMAGE_QUALITY`

JPEG compression quality (1-100).

**Format:** Integer (1-100)

**Default:** `85`

**Example:**
```bash
IMAGE_QUALITY=85
```

**Recommendations:**
- High quality: 90-95
- Balanced: 80-85
- Smaller files: 70-75

---

## Environment-Specific Examples

### Development Environment

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/pet_breeding_dev

# Authentication
SECRET_KEY=dev-secret-key-change-in-production
JWT_LIFETIME_SECONDS=3600

# Storage
STORAGE_PATH=storage/app
STORAGE_URL=/storage

# Application
APP_NAME=Pet Breeding API (Dev)
DEBUG=True
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4200

# Server
HOST=0.0.0.0
PORT=8000

# Redis
REDIS_URL=redis://localhost:6379/0

# Geocoding
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0-dev
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=3600

# Images
MAX_IMAGE_SIZE_MB=10
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
IMAGE_MAX_WIDTH=1920
IMAGE_MAX_HEIGHT=1920
IMAGE_QUALITY=85
```

### Production Environment

```bash
# Database
DATABASE_URL=postgresql+asyncpg://prod_user:secure_password@db.example.com:5432/pet_breeding_prod

# Authentication
SECRET_KEY=<generate-secure-random-key-32-chars-minimum>
JWT_LIFETIME_SECONDS=3600

# Storage
STORAGE_PATH=/var/www/pet-breeding/storage
STORAGE_URL=/storage

# Application
APP_NAME=Pet Breeding API
DEBUG=False
ALLOWED_ORIGINS=https://app.example.com,https://www.example.com

# Server
HOST=0.0.0.0
PORT=8000

# Redis
REDIS_URL=redis://:secure_password@redis.example.com:6379/0

# Geocoding
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=86400

# Images
MAX_IMAGE_SIZE_MB=10
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
IMAGE_MAX_WIDTH=1920
IMAGE_MAX_HEIGHT=1920
IMAGE_QUALITY=85
```

### Testing Environment

```bash
# Database
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db

# Authentication
SECRET_KEY=test-secret-key
JWT_LIFETIME_SECONDS=3600

# Storage
STORAGE_PATH=storage/test
STORAGE_URL=/storage

# Application
APP_NAME=Pet Breeding API (Test)
DEBUG=True
ALLOWED_ORIGINS=*

# Server
HOST=0.0.0.0
PORT=8000

# Redis
REDIS_URL=redis://localhost:6379/1

# Geocoding
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0-test
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=60

# Images
MAX_IMAGE_SIZE_MB=5
ALLOWED_IMAGE_TYPES=image/jpeg,image/png
IMAGE_MAX_WIDTH=1024
IMAGE_MAX_HEIGHT=1024
IMAGE_QUALITY=75
```

---

## Validation

### Check All Variables

```bash
# Load and display configuration
poetry run python -c "from app.config import settings; import json; print(json.dumps(settings.model_dump(), indent=2, default=str))"
```

### Test Database Connection

```bash
poetry run python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect()); print('Database OK')"
```

### Test Redis Connection

```bash
poetry run python -c "import redis; r = redis.from_url('redis://localhost:6379/0'); r.ping(); print('Redis OK')"
```

### Test Geocoding

```bash
# Start application
poetry run uvicorn app.main:app --reload

# Test geocoding endpoint
curl "http://localhost:8000/api/geocode/zip?zip=10001"
```

---

## Security Best Practices

1. **Never commit `.env` files** to version control
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use different keys** for each environment
   - Development: Simple key for convenience
   - Staging: Secure key, different from production
   - Production: Highly secure, rotated regularly

3. **Rotate secrets regularly**
   - Change `SECRET_KEY` every 90 days
   - Update Redis password quarterly
   - Rotate database credentials annually

4. **Use secrets management** in production
   - AWS Secrets Manager
   - HashiCorp Vault
   - Azure Key Vault
   - Environment variables in container orchestration

5. **Restrict access** to `.env` files
   ```bash
   chmod 600 .env
   ```

6. **Validate configuration** on startup
   - Application validates all required variables
   - Fails fast with clear error messages
   - Logs configuration issues (without exposing secrets)

---

## Troubleshooting

### Missing Required Variable

**Error:**
```
ValidationError: 1 validation error for Settings
DATABASE_URL
  field required (type=value_error.missing)
```

**Solution:**
- Add the missing variable to `.env`
- Ensure `.env` file is in the correct location
- Check for typos in variable names

### Invalid Database URL

**Error:**
```
sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from string
```

**Solution:**
- Verify URL format: `postgresql+asyncpg://user:pass@host:port/db`
- Check for special characters in password (URL encode if needed)
- Ensure asyncpg driver is specified

### Redis Connection Failed

**Error:**
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solution:**
- Verify Redis is running: `redis-cli ping`
- Check `REDIS_URL` format
- Verify host and port are correct
- Check firewall rules

### Geocoding Rate Limit

**Error:**
```
HTTPException: 429 Too Many Requests
```

**Solution:**
- Verify Redis caching is working
- Check cache hit rate: `redis-cli keys "geocode:*"`
- Ensure `GEOCODING_RATE_LIMIT` is 1.0 or less
- Consider local Nominatim instance for high volume

---

## Related Documentation

- [Main README](../README.md)
- [Pet Search Map API Documentation](PET_SEARCH_MAP_API.md)
- [Geocoding Service Documentation](GEOCODING_SERVICE.md)
- [Deployment Checklist](DEPLOYMENT_CHECKLIST.md)
