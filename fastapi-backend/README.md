# Pet Breeding Management API - FastAPI

Modern Python implementation of the pet breeding management system using FastAPI. This is a complete migration from the Laravel-based backend, maintaining API compatibility while leveraging modern Python async patterns.

## Features

- RESTful API for pet breeding management
- JWT-based authentication with fastapi-users
- Async database operations with SQLAlchemy 2.0
- Database migrations with Alembic
- Image upload and processing with Pillow
- Comprehensive test suite with property-based testing using Hypothesis
- UUID primary keys for all main entities
- Soft deletion support for pets
- Health record tracking (microchip, vaccination, certificates)
- Location and litter management
- **Pet Search with Map**: Location-based search with PostGIS and geocoding

## Requirements

### System Requirements
- Python 3.11 or higher
- PostgreSQL 12 or higher with PostGIS 3.0+ extension
- Redis 6.0 or higher (for geocoding cache)
- Poetry 1.5+ for dependency management
- 256MB minimum memory (512MB recommended)
- Disk space for image storage (varies by usage)

### Python Dependencies
All dependencies are managed through Poetry. Key dependencies include:
- FastAPI 0.109+
- SQLAlchemy 2.0+ (with asyncpg)
- GeoAlchemy2 (PostGIS support)
- Alembic (database migrations)
- fastapi-users (authentication)
- Pillow (image processing)
- Pydantic v2 (validation)
- Redis (caching)
- httpx (HTTP client for geocoding)
- aiolimiter (rate limiting)
- pytest + Hypothesis (testing)

## Installation

### 1. Clone and Navigate to Project

```bash
cd pets.backend.dev/fastapi-backend
```

### 2. Install Poetry (if not already installed)

```bash
# On macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -

# On Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# Verify installation
poetry --version
```

### 3. Install Dependencies

```bash
# Install all dependencies (including dev dependencies)
poetry install

# Install only production dependencies
poetry install --no-dev
```

### 4. Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your configuration
# Required variables:
# - DATABASE_URL: PostgreSQL connection string
# - SECRET_KEY: Secure random string (min 32 characters)
# - ALLOWED_ORIGINS: CORS origins for your frontend
```

**Important Configuration Notes:**

- **DATABASE_URL**: Must use `postgresql+asyncpg://` driver for async support
  - Format: `postgresql+asyncpg://user:password@host:port/database`
  - Example: `postgresql+asyncpg://postgres:password@localhost:5432/pet_breeding_db`

- **SECRET_KEY**: Generate a secure random key:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- **STORAGE_PATH**: Directory for uploaded images (created automatically)
  - Default: `storage/app`
  - Ensure write permissions

- **ALLOWED_ORIGINS**: Comma-separated list of frontend URLs
  - Example: `http://localhost:3000,http://localhost:4200,https://yourdomain.com`

### 5. Set Up Database

```bash
# Create the database (if not exists)
createdb pet_breeding_db

# Or using psql
psql -U postgres -c "CREATE DATABASE pet_breeding_db;"

# Run migrations to create tables
poetry run alembic upgrade head
```

### 6. Verify Installation

```bash
# Check that all dependencies are installed
poetry show

# Verify database connection
poetry run python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect())"
```

## Running the Application

### Development Mode

Start the development server with auto-reload:

```bash
# Using uvicorn directly
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using the main.py entry point
poetry run python -m app.main
```

The API will be available at:
- API Base: http://localhost:8000/api
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

### Production Mode

For production deployment, use multiple workers and disable reload:

```bash
# With 4 worker processes
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# With Gunicorn (recommended for production)
poetry run gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Production Checklist:**
- [ ] Set `DEBUG=False` in .env
- [ ] Use a strong `SECRET_KEY` (32+ characters)
- [ ] Configure proper `ALLOWED_ORIGINS` for CORS
- [ ] Set up HTTPS/TLS termination (nginx, load balancer)
- [ ] Configure database connection pooling
- [ ] Set up log rotation and monitoring
- [ ] Configure file storage backup
- [ ] Run migrations before deployment

### Docker Deployment (Optional)

```bash
# Build Docker image
docker build -t pet-breeding-api .

# Run container
docker run -d \
  --name pet-breeding-api \
  -p 8000:8000 \
  --env-file .env \
  pet-breeding-api
```

## Pet Search with Map Feature

The Pet Search with Map feature enables location-based discovery of pets and breeders using an interactive map interface powered by OpenStreetMap and Leaflet.js.

### Key Capabilities

- **Geospatial Search**: Find breeders within a specified radius using PostGIS spatial queries
- **Breed Filtering**: Search for specific dog breeds with autocomplete
- **Geocoding**: Convert ZIP codes to coordinates and vice versa
- **Interactive Map**: Display breeding locations on an interactive map with clustering
- **Public Access**: Search available to guests without authentication
- **Performance**: Optimized queries with spatial indexing and Redis caching

### Architecture

```
User → Frontend (Angular + Leaflet) → Backend API → PostGIS Database
                                    ↓
                              Nominatim (Geocoding)
                                    ↓
                              Redis (Cache)
```

### Prerequisites

#### 1. PostGIS Extension

Enable PostGIS in your PostgreSQL database:

```bash
# Install PostGIS (Ubuntu/Debian)
sudo apt-get install postgresql-12-postgis-3

# Or macOS (Homebrew)
brew install postgis

# Enable in database
psql -U postgres -d pet_breeding_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Verify
psql -U postgres -d pet_breeding_db -c "SELECT PostGIS_version();"
```

See [POSTGIS_SETUP_SUMMARY.md](POSTGIS_SETUP_SUMMARY.md) for detailed setup instructions.

#### 2. Redis Server

Install and start Redis for geocoding cache:

```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Or macOS (Homebrew)
brew install redis

# Start Redis
redis-server

# Verify
redis-cli ping  # Should return: PONG
```

#### 3. Environment Configuration

Add these variables to your `.env` file:

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Geocoding Configuration
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=86400
```

### API Endpoints

The feature adds the following public endpoints:

#### Search Breeders
```bash
GET /api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40&breed_id=123
```

Returns breeding locations within the specified radius, optionally filtered by breed.

#### Breed Autocomplete
```bash
GET /api/breeds/autocomplete?search_term=gold
```

Returns breed suggestions for autocomplete functionality.

#### Geocode ZIP Code
```bash
GET /api/geocode/zip?zip=10001
```

Converts a US ZIP code to coordinates.

#### Reverse Geocode
```bash
GET /api/geocode/reverse?lat=40.7506&lon=-73.9971
```

Converts coordinates to an address.

### Performance Features

- **Spatial Indexing**: PostGIS GIST index for sub-100ms queries
- **Geocoding Cache**: 24-hour Redis cache (90%+ hit rate)
- **Rate Limiting**: Automatic 1 req/sec throttling for Nominatim
- **Query Optimization**: Efficient spatial queries with ST_DWithin

### Testing

The feature includes comprehensive tests:

```bash
# Run all tests
poetry run pytest

# Run geospatial tests only
poetry run pytest tests/property/test_breeder_search_properties.py
poetry run pytest tests/integration/test_search_endpoints.py

# Run with coverage
poetry run pytest --cov=app.services.breeder_service --cov=app.services.geocoding_service
```

### Documentation

Detailed documentation available:

- **[Pet Search Map API Documentation](docs/PET_SEARCH_MAP_API.md)**: Complete API reference with examples
- **[Geocoding Service Documentation](docs/GEOCODING_SERVICE.md)**: Geocoding service usage and configuration
- **[Deployment Checklist](docs/DEPLOYMENT_CHECKLIST.md)**: Step-by-step deployment guide
- **[PostGIS Setup](POSTGIS_SETUP_SUMMARY.md)**: PostGIS installation and configuration

### Quick Start

1. **Enable PostGIS**:
   ```bash
   psql -U postgres -d pet_breeding_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
   ```

2. **Start Redis**:
   ```bash
   redis-server
   ```

3. **Run Migrations**:
   ```bash
   poetry run alembic upgrade head
   ```

4. **Start Application**:
   ```bash
   poetry run uvicorn app.main:app --reload
   ```

5. **Test Endpoints**:
   ```bash
   # Test breeder search
   curl "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"
   
   # Test geocoding
   curl "http://localhost:8000/api/geocode/zip?zip=10001"
   ```

### Troubleshooting

**PostGIS not available:**
```bash
# Check if PostGIS is installed
psql -U postgres -d pet_breeding_db -c "SELECT PostGIS_version();"

# If not, install and enable
sudo apt-get install postgresql-12-postgis-3
psql -U postgres -d pet_breeding_db -c "CREATE EXTENSION postgis;"
```

**Redis connection failed:**
```bash
# Check if Redis is running
redis-cli ping

# Start Redis if not running
redis-server
```

**Geocoding rate limit errors:**
- Ensure Redis caching is working (check `REDIS_URL` in .env)
- Verify cache hit rate: `redis-cli keys "geocode:*"`
- Do not increase `GEOCODING_RATE_LIMIT` above 1.0 for public Nominatim

For more troubleshooting, see the [Geocoding Service Documentation](docs/GEOCODING_SERVICE.md).

---

## API Documentation

Once the application is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/api/docs (interactive testing interface)
- **ReDoc**: http://localhost:8000/api/redoc (clean, readable documentation)
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json (machine-readable spec)

For detailed API usage examples with cURL and JavaScript code samples, see the [API Documentation](API_DOCUMENTATION.md) file.

### Quick API Overview

The API provides the following main endpoints:

- **Authentication** (`/api/auth/*`): User registration, login, password reset
- **Pets** (`/api/pets/*`): Pet CRUD operations and image uploads
- **Breeds** (`/api/breeds/*`): Breed management
- **Litters** (`/api/litters/*`): Litter tracking
- **Locations** (`/api/locations/*`): Location management

All endpoints (except registration and login) require JWT authentication via the `Authorization: Bearer <token>` header.

## Testing

The project includes a comprehensive test suite with unit tests, integration tests, and property-based tests.

### Test Database Setup

The test suite requires a PostgreSQL database. The easiest way to set this up is using Docker Compose:

```bash
# Start the test database
docker-compose -f docker-compose.test.yml up -d

# Verify the database is running
docker exec fastapi-test-db psql -U test -d test_db -c "SELECT 1"

# Stop the test database when done
docker-compose -f docker-compose.test.yml down
```

**Test Database Configuration:**
- Host: localhost:5432
- User: test
- Password: test
- Database: test_db

**Manual Setup (without Docker):**

```bash
# Create test database
createdb test_db

# Set environment variable for tests
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/test_db"
```

### Running Tests

**Run all tests:**

```bash
poetry run pytest
```

**Run with coverage report:**

```bash
# Terminal coverage report
poetry run pytest --cov=app --cov-report=term-missing

# HTML coverage report (opens in browser)
poetry run pytest --cov=app --cov-report=html
open htmlcov/index.html
```

**Run specific test categories:**

```bash
# Unit tests only
poetry run pytest tests/unit/

# Integration tests only
poetry run pytest tests/integration/

# Property-based tests only
poetry run pytest tests/property/

# Specific test file
poetry run pytest tests/unit/test_config.py

# Specific test function
poetry run pytest tests/unit/test_config.py::test_config_loads_from_env
```

**Property-Based Testing:**

Property tests use Hypothesis to generate random test data. By default, each property test runs 100 examples.

```bash
# Run with more examples (thorough testing)
poetry run pytest --hypothesis-max-examples=1000 tests/property/

# Run with fewer examples (faster feedback)
poetry run pytest --hypothesis-max-examples=10 tests/property/

# Show Hypothesis statistics
poetry run pytest --hypothesis-show-statistics tests/property/
```

**Test Output Options:**

```bash
# Verbose output
poetry run pytest -v

# Show print statements
poetry run pytest -s

# Stop on first failure
poetry run pytest -x

# Run last failed tests
poetry run pytest --lf

# Run tests in parallel (requires pytest-xdist)
poetry run pytest -n auto
```

**Continuous Testing:**

```bash
# Watch for changes and re-run tests (requires pytest-watch)
poetry run ptw
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_schemas.py
│   ├── test_file_service.py
│   └── ...
├── integration/             # Integration tests (API endpoints)
│   ├── test_auth_endpoints.py
│   ├── test_pet_endpoints.py
│   ├── test_breed_endpoints.py
│   └── ...
└── property/                # Property-based tests (Hypothesis)
    ├── test_uuid_properties.py
    ├── test_auth_properties.py
    ├── test_validation_properties.py
    └── ...
```

### Coverage Goals

- **Minimum Coverage**: 80%
- **Target Coverage**: 90%+
- **Critical Paths**: 100% (authentication, data validation)

Check current coverage:

```bash
poetry run pytest --cov=app --cov-report=term-missing | grep TOTAL
```

## Database Migrations

Alembic manages all database schema changes through version-controlled migration files.

### Common Migration Commands

**Create a new migration:**

```bash
# Auto-generate migration from model changes
poetry run alembic revision --autogenerate -m "Description of changes"

# Create empty migration (for data migrations)
poetry run alembic revision -m "Description of changes"
```

**Apply migrations:**

```bash
# Upgrade to latest version
poetry run alembic upgrade head

# Upgrade to specific version
poetry run alembic upgrade <revision_id>

# Upgrade one version forward
poetry run alembic upgrade +1
```

**Rollback migrations:**

```bash
# Rollback one version
poetry run alembic downgrade -1

# Rollback to specific version
poetry run alembic downgrade <revision_id>

# Rollback all migrations
poetry run alembic downgrade base
```

**View migration history:**

```bash
# Show all migrations
poetry run alembic history

# Show current version
poetry run alembic current

# Show pending migrations
poetry run alembic heads
```

### Migration Best Practices

1. **Always review auto-generated migrations** before applying
2. **Test migrations on a copy of production data** before deploying
3. **Write reversible migrations** (implement both upgrade and downgrade)
4. **Keep migrations small and focused** (one logical change per migration)
5. **Never edit applied migrations** (create a new migration instead)
6. **Backup database before running migrations** in production

### Migration Workflow

```bash
# 1. Make changes to SQLAlchemy models
# 2. Generate migration
poetry run alembic revision --autogenerate -m "Add pet health_score field"

# 3. Review generated migration file in alembic/versions/
# 4. Test migration on development database
poetry run alembic upgrade head

# 5. Test rollback
poetry run alembic downgrade -1

# 6. Re-apply migration
poetry run alembic upgrade head

# 7. Commit migration file to version control
git add alembic/versions/<new_migration>.py
git commit -m "Add pet health_score field migration"
```

### Troubleshooting Migrations

**Migration conflicts:**

```bash
# If you have multiple heads (branches)
poetry run alembic merge heads -m "Merge migration branches"
```

**Reset migrations (development only):**

```bash
# WARNING: This will delete all data!
poetry run alembic downgrade base
dropdb pet_breeding_db
createdb pet_breeding_db
poetry run alembic upgrade head
```

**Check migration SQL without applying:**

```bash
poetry run alembic upgrade head --sql
```

## Project Structure

```
fastapi-backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # Database session management
│   ├── dependencies.py      # FastAPI dependencies
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── routers/             # API route handlers
│   └── services/            # Business logic
├── alembic/                 # Database migrations
├── tests/                   # Test suite
├── storage/                 # File storage
├── pyproject.toml           # Project dependencies
├── .env.example             # Example environment variables
└── README.md
```

## Configuration

All configuration is managed through environment variables defined in `.env` file.

### Required Configuration Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string with asyncpg driver | `postgresql+asyncpg://user:pass@localhost:5432/db` | Yes |
| `SECRET_KEY` | Secret key for JWT token generation (min 32 chars) | `your-secret-key-here` | Yes |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:3000,http://localhost:4200` | Yes |

### Optional Configuration Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `JWT_LIFETIME_SECONDS` | JWT token lifetime in seconds | `3600` | `7200` |
| `STORAGE_PATH` | Directory for uploaded files | `storage/app` | `/var/www/storage` |
| `STORAGE_URL` | Public URL path for files | `/storage` | `/media` |
| `APP_NAME` | Application name | `Pet Breeding API` | `My Pet API` |
| `DEBUG` | Enable debug mode | `False` | `True` |
| `HOST` | Server host | `0.0.0.0` | `127.0.0.1` |
| `PORT` | Server port | `8000` | `8080` |
| `MAX_IMAGE_SIZE_MB` | Max image upload size (MB) | `10` | `20` |
| `ALLOWED_IMAGE_TYPES` | Comma-separated image MIME types | `image/jpeg,image/png,image/webp` | `image/jpeg` |
| `IMAGE_MAX_WIDTH` | Max image width (pixels) | `1920` | `2560` |
| `IMAGE_MAX_HEIGHT` | Max image height (pixels) | `1920` | `2560` |
| `IMAGE_QUALITY` | JPEG quality (1-100) | `85` | `90` |

### Environment-Specific Configuration

**Development (.env.development):**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/pet_breeding_dev
SECRET_KEY=dev-secret-key-change-in-production
DEBUG=True
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4200
```

**Production (.env.production):**

```bash
DATABASE_URL=postgresql+asyncpg://prod_user:secure_password@db.example.com:5432/pet_breeding_prod
SECRET_KEY=<generate-secure-random-key>
DEBUG=False
ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
JWT_LIFETIME_SECONDS=3600
STORAGE_PATH=/var/www/pet-breeding/storage
```

**Testing (.env.test):**

```bash
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db
SECRET_KEY=test-secret-key
DEBUG=True
ALLOWED_ORIGINS=*
```

### Configuration Validation

The application validates all required configuration on startup. If any required variable is missing or invalid, the application will fail to start with a clear error message.

```bash
# Test configuration
poetry run python -c "from app.config import settings; print(settings.model_dump())"
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/jwt/login` - Login and get JWT token
- `POST /api/auth/jwt/logout` - Logout
- `POST /api/auth/forgot-password` - Request password reset
- `POST /api/auth/reset-password` - Reset password
- `POST /api/auth/request-verify-token` - Request email verification
- `POST /api/auth/verify` - Verify email

### Pets
- `POST /api/pets` - Create new pet
- `GET /api/pets` - List user's pets
- `GET /api/pets/{pet_id}` - Get pet details
- `PUT /api/pets/{pet_id}` - Update pet
- `DELETE /api/pets/{pet_id}` - Soft delete pet
- `GET /api/pets/breeder/{breeder_id}` - Get pets by breeder
- `POST /api/pets/{pet_id}/image` - Upload pet image

### Breeds
- `POST /api/breeds` - Create breed
- `GET /api/breeds` - List all breeds
- `GET /api/breeds/{breed_id}` - Get breed details
- `PUT /api/breeds/{breed_id}` - Update breed
- `DELETE /api/breeds/{breed_id}` - Delete breed

### Litters
- `POST /api/litters` - Create litter
- `GET /api/litters` - List litters
- `GET /api/litters/{litter_id}` - Get litter details
- `PUT /api/litters/{litter_id}` - Update litter
- `DELETE /api/litters/{litter_id}` - Delete litter

### Locations
- `POST /api/locations` - Create location
- `GET /api/locations` - List user's locations
- `GET /api/locations/{location_id}` - Get location details
- `PUT /api/locations/{location_id}` - Update location
- `DELETE /api/locations/{location_id}` - Delete location

For detailed API documentation with request/response examples, see the [API Documentation](#api-documentation) section or visit the interactive docs at `/api/docs` when the server is running.

## Migration from Laravel

This FastAPI implementation maintains API compatibility with the original Laravel backend. Key migration notes:

### Database Compatibility
- Uses the same PostgreSQL database schema
- UUID primary keys preserved for all main entities
- Foreign key relationships maintained
- Soft deletion implemented via `is_deleted` flag

### Authentication Migration
- Laravel Sanctum tokens are not compatible with JWT tokens
- Users will need to re-authenticate after migration
- Password hashes are compatible (both use bcrypt)
- User data (email, profile) is preserved

### API Compatibility
- All endpoints maintain the same URL structure (`/api/...`)
- Request/response JSON formats are identical
- HTTP status codes match Laravel implementation
- Error response formats are consistent

### Migration Steps

1. **Backup Laravel database:**
   ```bash
   pg_dump laravel_db > backup.sql
   ```

2. **Run FastAPI migrations:**
   ```bash
   poetry run alembic upgrade head
   ```

3. **Verify data integrity:**
   ```bash
   # Check record counts match
   psql -d pet_breeding_db -c "SELECT COUNT(*) FROM users;"
   psql -d pet_breeding_db -c "SELECT COUNT(*) FROM pets;"
   ```

4. **Update frontend configuration:**
   - Update API base URL if changed
   - Update authentication flow to use JWT
   - Test all API integrations

5. **Deploy FastAPI application:**
   ```bash
   poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

### Feature Parity

| Feature | Laravel | FastAPI | Status |
|---------|---------|---------|--------|
| User Authentication | ✅ Sanctum | ✅ JWT | ✅ Complete |
| Pet CRUD | ✅ | ✅ | ✅ Complete |
| Breed Management | ✅ | ✅ | ✅ Complete |
| Litter Management | ✅ | ✅ | ✅ Complete |
| Location Management | ✅ | ✅ | ✅ Complete |
| Image Upload | ✅ | ✅ | ✅ Complete |
| Health Records | ✅ | ✅ | ✅ Complete |
| Soft Deletion | ✅ | ✅ | ✅ Complete |
| UUID Primary Keys | ✅ | ✅ | ✅ Complete |
| Async Operations | ❌ | ✅ | ✅ Enhanced |
| Property-Based Tests | ❌ | ✅ | ✅ Enhanced |

## Development

### Code Style

The project uses Ruff for linting and formatting:

```bash
# Check for linting issues
poetry run ruff check app/

# Auto-fix linting issues
poetry run ruff check --fix app/

# Format code
poetry run ruff format app/

# Check and format all code
poetry run ruff check --fix app/ && poetry run ruff format app/
```

### Type Checking

Type checking with mypy:

```bash
# Check types
poetry run mypy app/

# Check with strict mode
poetry run mypy --strict app/
```

### Pre-commit Hooks (Optional)

Set up pre-commit hooks to automatically check code before commits:

```bash
# Install pre-commit
poetry add --group dev pre-commit

# Install hooks
poetry run pre-commit install

# Run hooks manually
poetry run pre-commit run --all-files
```

## Troubleshooting

### Common Issues

**Issue: Database connection fails**

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution:**
- Verify PostgreSQL is running: `pg_isready`
- Check DATABASE_URL format: `postgresql+asyncpg://user:pass@host:port/db`
- Ensure database exists: `createdb pet_breeding_db`
- Check firewall/network settings

**Issue: Migration fails with "target database is not up to date"**

```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solution:**
```bash
# Check current version
poetry run alembic current

# View migration history
poetry run alembic history

# Upgrade to head
poetry run alembic upgrade head
```

**Issue: Import errors or module not found**

```
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```bash
# Reinstall dependencies
poetry install

# Verify virtual environment is activated
poetry shell

# Check Python path
poetry run python -c "import sys; print(sys.path)"
```

**Issue: Tests fail with database errors**

```
asyncpg.exceptions.InvalidCatalogNameError: database "test_db" does not exist
```

**Solution:**
```bash
# Create test database
createdb test_db

# Or use Docker Compose
docker-compose -f docker-compose.test.yml up -d

# Set test database URL
export TEST_DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test_db"
```

**Issue: Image upload fails**

```
PermissionError: [Errno 13] Permission denied: 'storage/app'
```

**Solution:**
```bash
# Create storage directory with proper permissions
mkdir -p storage/app
chmod 755 storage/app

# Or set custom storage path in .env
STORAGE_PATH=/path/to/writable/directory
```

**Issue: CORS errors in browser**

```
Access to fetch at 'http://localhost:8000/api/pets' from origin 'http://localhost:3000' has been blocked by CORS policy
```

**Solution:**
- Add frontend URL to ALLOWED_ORIGINS in .env:
  ```bash
  ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4200
  ```
- Restart the application after changing .env

### Debug Mode

Enable debug mode for detailed error messages:

```bash
# In .env
DEBUG=True

# Run with debug logging
poetry run uvicorn app.main:app --reload --log-level debug
```

### Performance Optimization

**Database Connection Pooling:**

```python
# In app/database.py, configure pool settings
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Number of connections to maintain
    max_overflow=10,       # Additional connections when pool is full
    pool_pre_ping=True,    # Verify connections before using
    pool_recycle=3600,     # Recycle connections after 1 hour
)
```

**Caching:**

Consider adding Redis for caching frequently accessed data:

```bash
poetry add redis aioredis
```

**Query Optimization:**

- Use `selectinload()` or `joinedload()` for eager loading relationships
- Add database indexes for frequently queried fields
- Use pagination for large result sets

### Monitoring and Logging

**Application Logs:**

```bash
# View logs in real-time
tail -f logs/app.log

# Search logs
grep "ERROR" logs/app.log

# View last 100 lines
tail -n 100 logs/app.log
```

**Database Query Logging:**

Enable SQLAlchemy query logging in development:

```python
# In app/database.py
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Log all SQL queries
)
```

**Health Check Endpoint:**

```bash
# Check application health
curl http://localhost:8000/health

# Check database connectivity
curl http://localhost:8000/health/db
```

## License

Proprietary - Pet Breeding Management System

## Contributing

### Development Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes and write tests:**
   - Write unit tests for new functions
   - Write integration tests for new endpoints
   - Write property tests for universal properties
   - Ensure all tests pass: `poetry run pytest`

3. **Check code quality:**
   ```bash
   # Format code
   poetry run ruff format app/
   
   # Check linting
   poetry run ruff check --fix app/
   
   # Type checking
   poetry run mypy app/
   
   # Run tests with coverage
   poetry run pytest --cov=app --cov-report=term-missing
   ```

4. **Create migration if needed:**
   ```bash
   poetry run alembic revision --autogenerate -m "Description"
   ```

5. **Commit changes:**
   ```bash
   git add .
   git commit -m "feat: Add your feature description"
   ```

6. **Push and create pull request:**
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

Follow conventional commits format:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions or changes
- `refactor:` Code refactoring
- `perf:` Performance improvements
- `chore:` Build process or auxiliary tool changes

Examples:
```
feat: Add pet health score calculation
fix: Resolve image upload permission issue
docs: Update API endpoint documentation
test: Add property tests for UUID generation
```

### Code Review Checklist

- [ ] All tests pass
- [ ] Code coverage is maintained or improved
- [ ] Code follows project style guidelines
- [ ] Documentation is updated
- [ ] Migration files are included (if schema changed)
- [ ] No sensitive data in commits
- [ ] Error handling is comprehensive
- [ ] Logging is appropriate

## Support

For issues, questions, or contributions:

1. Check existing documentation
2. Search closed issues on GitHub
3. Create a new issue with detailed description
4. Include error messages, logs, and reproduction steps

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Authentication by [fastapi-users](https://fastapi-users.github.io/fastapi-users/)
- ORM by [SQLAlchemy](https://www.sqlalchemy.org/)
- Testing with [pytest](https://pytest.org/) and [Hypothesis](https://hypothesis.readthedocs.io/)

---

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Python Version:** 3.11+  
**FastAPI Version:** 0.109+
