# Pet Search with Map - Deployment Checklist

## Overview

This checklist ensures all components of the Pet Search with Map feature are properly configured and deployed. Complete each section in order before deploying to production.

---

## Pre-Deployment Requirements

### 1. Database Requirements

#### PostgreSQL Version
- [ ] PostgreSQL 12 or higher installed
- [ ] Database created and accessible
- [ ] Database user has CREATE EXTENSION privileges

**Verification:**
```bash
psql --version
# Should show: PostgreSQL 12.x or higher

psql -U your_user -d your_database -c "SELECT version();"
```

#### PostGIS Extension
- [ ] PostGIS extension available
- [ ] PostGIS version 3.0 or higher

**Installation:**
```bash
# Ubuntu/Debian
sudo apt-get install postgresql-12-postgis-3

# macOS (Homebrew)
brew install postgis

# Verify installation
psql -U your_user -d your_database -c "SELECT PostGIS_version();"
```

**Enable PostGIS:**
```sql
-- Connect to your database
psql -U your_user -d your_database

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Verify
SELECT PostGIS_version();
-- Should return version like: 3.1 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
```

- [ ] PostGIS extension enabled in database
- [ ] PostGIS functions accessible

**Verification:**
```sql
-- Test PostGIS functions
SELECT ST_Distance(
    ST_MakePoint(-73.9855, 40.7580),
    ST_MakePoint(-74.0060, 40.7128)
);
-- Should return a distance value
```

### 2. Redis Requirements

#### Redis Installation
- [ ] Redis 6.0 or higher installed
- [ ] Redis server running
- [ ] Redis accessible from application server

**Installation:**
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS (Homebrew)
brew install redis

# Start Redis
redis-server

# Verify
redis-cli ping
# Should return: PONG
```

#### Redis Configuration
- [ ] Redis persistence enabled (optional but recommended)
- [ ] Redis password set (production only)
- [ ] Redis maxmemory policy configured

**Configuration (redis.conf):**
```conf
# Persistence
save 900 1
save 300 10
save 60 10000

# Memory management
maxmemory 256mb
maxmemory-policy allkeys-lru

# Security (production)
requirepass your_secure_password
```

- [ ] Redis connection tested from application

**Verification:**
```bash
# Test connection
redis-cli -h localhost -p 6379 ping

# Test with password (if set)
redis-cli -h localhost -p 6379 -a your_password ping

# Test from Python
python -c "import redis; r = redis.from_url('redis://localhost:6379/0'); print(r.ping())"
```

### 3. Python Environment

#### Python Version
- [ ] Python 3.11 or higher installed
- [ ] Poetry 1.5+ installed for dependency management

**Verification:**
```bash
python --version
# Should show: Python 3.11.x or higher

poetry --version
# Should show: Poetry (version 1.5.x)
```

#### Dependencies
- [ ] All Python dependencies installed
- [ ] GeoAlchemy2 installed for PostGIS support
- [ ] Redis client (redis-py) installed
- [ ] aiolimiter installed for rate limiting
- [ ] httpx installed for HTTP requests

**Installation:**
```bash
cd pets.backend.dev/fastapi-backend
poetry install
```

**Verification:**
```bash
poetry show | grep -E "geoalchemy2|redis|aiolimiter|httpx"
# Should show all packages installed
```

---

## Configuration

### 1. Environment Variables

Create or update `.env` file with the following variables:

#### Required Variables

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
# Or with password:
# REDIS_URL=redis://:password@localhost:6379/0

# Geocoding Configuration
NOMINATIM_URL=https://nominatim.openstreetmap.org
GEOCODING_USER_AGENT=BreedyPetSearch/1.0
GEOCODING_RATE_LIMIT=1.0
GEOCODING_CACHE_TTL=86400

# Application Configuration
SECRET_KEY=your-secret-key-here-change-in-production
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
DEBUG=False
```

#### Checklist

- [ ] `DATABASE_URL` set with correct credentials
- [ ] `REDIS_URL` set with correct host and port
- [ ] `NOMINATIM_URL` set (default: https://nominatim.openstreetmap.org)
- [ ] `GEOCODING_USER_AGENT` set to your application name/version
- [ ] `GEOCODING_RATE_LIMIT` set to 1.0 (do not increase for public Nominatim)
- [ ] `GEOCODING_CACHE_TTL` set (default: 86400 = 24 hours)
- [ ] `SECRET_KEY` set to secure random value (min 32 characters)
- [ ] `ALLOWED_ORIGINS` set to your frontend URLs
- [ ] `DEBUG` set to False for production

**Generate Secure Secret Key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Configuration Validation

- [ ] All required environment variables present
- [ ] Database connection successful
- [ ] Redis connection successful
- [ ] Configuration loads without errors

**Verification:**
```bash
# Test configuration
poetry run python -c "from app.config import settings; print('Config OK')"

# Test database connection
poetry run python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect()); print('Database OK')"

# Test Redis connection
poetry run python -c "import redis; r = redis.from_url('redis://localhost:6379/0'); r.ping(); print('Redis OK')"
```

---

## Database Migrations

### 1. Run Migrations

- [ ] Alembic initialized
- [ ] All migrations reviewed
- [ ] Migrations tested on development database
- [ ] Backup of production database created (if applicable)

**Run Migrations:**
```bash
cd pets.backend.dev/fastapi-backend

# Check current migration status
poetry run alembic current

# View pending migrations
poetry run alembic history

# Run migrations
poetry run alembic upgrade head
```

### 2. Verify PostGIS Setup

- [ ] `locations` table has `coordinates` column
- [ ] `coordinates` column is of type `geometry(Point, 4326)`
- [ ] Spatial index exists on `coordinates` column

**Verification:**
```sql
-- Check column exists
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'locations' AND column_name = 'coordinates';

-- Check spatial index
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'locations' AND indexname LIKE '%coordinates%';

-- Test spatial query
SELECT COUNT(*)
FROM locations
WHERE coordinates IS NOT NULL;
```

### 3. Populate Geometry Data

If migrating from existing data with separate lat/lon columns:

- [ ] Existing latitude/longitude data identified
- [ ] Geometry column populated from lat/lon
- [ ] All locations have valid coordinates

**Migration Script:**
```sql
-- Populate coordinates from lat/lon (if applicable)
UPDATE locations
SET coordinates = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
WHERE latitude IS NOT NULL 
  AND longitude IS NOT NULL 
  AND coordinates IS NULL;

-- Verify
SELECT COUNT(*) FROM locations WHERE coordinates IS NOT NULL;
```

---

## Application Deployment

### 1. Code Deployment

- [ ] Latest code pulled from repository
- [ ] Dependencies installed
- [ ] Static files collected (if applicable)
- [ ] File permissions set correctly

**Deployment Steps:**
```bash
# Pull latest code
git pull origin main

# Install dependencies
poetry install --no-dev

# Verify installation
poetry run python -c "import app; print('Import OK')"
```

### 2. Service Configuration

#### Systemd Service (Linux)

Create `/etc/systemd/system/pet-breeding-api.service`:

```ini
[Unit]
Description=Pet Breeding API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/pet-breeding-api
Environment="PATH=/var/www/pet-breeding-api/.venv/bin"
ExecStart=/var/www/pet-breeding-api/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

- [ ] Service file created
- [ ] Service enabled
- [ ] Service started

**Commands:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable pet-breeding-api
sudo systemctl start pet-breeding-api
sudo systemctl status pet-breeding-api
```

#### Docker Deployment (Alternative)

- [ ] Dockerfile created
- [ ] Docker image built
- [ ] Container running
- [ ] Health check passing

**Docker Commands:**
```bash
# Build image
docker build -t pet-breeding-api:latest .

# Run container
docker run -d \
  --name pet-breeding-api \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  pet-breeding-api:latest

# Check logs
docker logs pet-breeding-api

# Check health
curl http://localhost:8000/health
```

### 3. Reverse Proxy Configuration

#### Nginx Configuration

Create `/etc/nginx/sites-available/pet-breeding-api`:

```nginx
upstream pet_breeding_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # API endpoints
    location /api/ {
        proxy_pass http://pet_breeding_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check
    location /health {
        proxy_pass http://pet_breeding_api;
        access_log off;
    }
}
```

- [ ] Nginx configuration created
- [ ] SSL certificate installed
- [ ] Configuration tested
- [ ] Nginx reloaded

**Commands:**
```bash
# Test configuration
sudo nginx -t

# Enable site
sudo ln -s /etc/nginx/sites-available/pet-breeding-api /etc/nginx/sites-enabled/

# Reload Nginx
sudo systemctl reload nginx
```

---

## Testing

### 1. Health Checks

- [ ] Application health endpoint responding
- [ ] Database connectivity verified
- [ ] Redis connectivity verified

**Tests:**
```bash
# Application health
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# API documentation accessible
curl http://localhost:8000/api/docs
# Should return HTML

# Test database
curl http://localhost:8000/health/db
# Expected: {"database": "connected"}
```

### 2. API Endpoint Tests

- [ ] Breeder search endpoint working
- [ ] Breed autocomplete endpoint working
- [ ] Geocoding endpoints working
- [ ] Error handling working

**Tests:**
```bash
# Test breeder search
curl "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"
# Expected: JSON array of breeders

# Test breed autocomplete
curl "http://localhost:8000/api/breeds/autocomplete?search_term=gold"
# Expected: JSON array of breeds

# Test ZIP geocoding
curl "http://localhost:8000/api/geocode/zip?zip=10001"
# Expected: {"latitude": 40.7506, "longitude": -73.9971}

# Test reverse geocoding
curl "http://localhost:8000/api/geocode/reverse?lat=40.7506&lon=-73.9971"
# Expected: {"zip_code": "10001", "city": "New York", ...}

# Test error handling
curl "http://localhost:8000/api/search/breeders?latitude=invalid"
# Expected: 400 error with validation message
```

### 3. Performance Tests

- [ ] Response times acceptable (< 500ms p95)
- [ ] Geocoding cache working (hit rate > 90%)
- [ ] Spatial queries optimized (< 100ms)
- [ ] Rate limiting working

**Tests:**
```bash
# Test response time
time curl "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"

# Test cache (second request should be faster)
time curl "http://localhost:8000/api/geocode/zip?zip=10001"
time curl "http://localhost:8000/api/geocode/zip?zip=10001"

# Check Redis cache
redis-cli keys "geocode:*"
redis-cli get "geocode:zip:10001"
```

### 4. Load Testing

- [ ] Load test with 100 concurrent users
- [ ] No errors under normal load
- [ ] Response times stable under load

**Load Test Script:**
```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Test breeder search (100 requests, 10 concurrent)
ab -n 100 -c 10 "http://localhost:8000/api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=40"

# Test geocoding (should be fast due to caching)
ab -n 100 -c 10 "http://localhost:8000/api/geocode/zip?zip=10001"
```

---

## Frontend Deployment

### 1. Frontend Configuration

- [ ] API base URL configured
- [ ] Environment variables set
- [ ] CORS origins match backend configuration

**Angular Environment File:**
```typescript
// src/environments/environment.prod.ts
export const environment = {
  production: true,
  apiUrl: 'https://api.yourdomain.com/api',
  mapTileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
};
```

### 2. Build and Deploy

- [ ] Production build created
- [ ] Assets optimized
- [ ] Source maps generated (optional)
- [ ] Files deployed to web server

**Build Commands:**
```bash
cd pets.frontend.dev

# Install dependencies
npm install

# Build for production
npm run build

# Deploy (example with rsync)
rsync -avz dist/ user@server:/var/www/pet-breeding-frontend/
```

### 3. Web Server Configuration

#### Nginx Configuration for Angular

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    root /var/www/pet-breeding-frontend;
    index index.html;

    # Angular routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

- [ ] Nginx configuration created
- [ ] SSL certificate installed
- [ ] Configuration tested
- [ ] Nginx reloaded

---

## Monitoring and Logging

### 1. Application Logging

- [ ] Log directory created with proper permissions
- [ ] Log rotation configured
- [ ] Error logs monitored

**Log Configuration:**
```python
# In app/main.py
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[handler]
)
```

### 2. Monitoring Setup

- [ ] Health check endpoint monitored
- [ ] Response time monitoring configured
- [ ] Error rate monitoring configured
- [ ] Database connection monitoring configured

**Monitoring Tools:**
- Uptime monitoring: UptimeRobot, Pingdom
- APM: New Relic, DataDog, Sentry
- Logs: ELK Stack, Splunk, CloudWatch

### 3. Alerts

- [ ] Alert for service down
- [ ] Alert for high error rate
- [ ] Alert for slow response times
- [ ] Alert for database connection failures
- [ ] Alert for Redis connection failures

---

## Security

### 1. SSL/TLS

- [ ] SSL certificate installed
- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] Certificate auto-renewal configured

**Let's Encrypt Setup:**
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d api.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

### 2. Firewall

- [ ] Firewall configured
- [ ] Only necessary ports open
- [ ] Database port not publicly accessible
- [ ] Redis port not publicly accessible

**UFW Configuration:**
```bash
# Enable firewall
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Deny direct database access
sudo ufw deny 5432/tcp

# Deny direct Redis access
sudo ufw deny 6379/tcp

# Check status
sudo ufw status
```

### 3. Application Security

- [ ] `DEBUG=False` in production
- [ ] Strong `SECRET_KEY` set
- [ ] CORS properly configured
- [ ] Rate limiting enabled
- [ ] Input validation enabled

---

## Backup and Recovery

### 1. Database Backup

- [ ] Automated backup configured
- [ ] Backup retention policy defined
- [ ] Backup restoration tested

**Backup Script:**
```bash
#!/bin/bash
# /usr/local/bin/backup-database.sh

BACKUP_DIR="/var/backups/postgresql"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="pet_breeding_db_$DATE.sql.gz"

# Create backup
pg_dump -U postgres pet_breeding_db | gzip > "$BACKUP_DIR/$FILENAME"

# Keep only last 30 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete

echo "Backup completed: $FILENAME"
```

**Cron Job:**
```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-database.sh
```

### 2. Redis Backup

- [ ] Redis persistence enabled
- [ ] RDB snapshots configured
- [ ] AOF enabled (optional)

**Redis Configuration:**
```conf
# RDB snapshots
save 900 1
save 300 10
save 60 10000

# AOF (optional)
appendonly yes
appendfsync everysec
```

### 3. Application Backup

- [ ] Code repository backed up
- [ ] Configuration files backed up
- [ ] Environment variables documented

---

## Documentation

### 1. API Documentation

- [ ] API documentation accessible at `/api/docs`
- [ ] All endpoints documented
- [ ] Example requests/responses provided
- [ ] Error codes documented

### 2. Deployment Documentation

- [ ] Deployment process documented
- [ ] Configuration variables documented
- [ ] Troubleshooting guide created
- [ ] Rollback procedure documented

### 3. Runbooks

- [ ] Service restart procedure
- [ ] Database migration procedure
- [ ] Cache clearing procedure
- [ ] Incident response procedure

---

## Post-Deployment

### 1. Smoke Tests

- [ ] All critical endpoints tested
- [ ] User workflows tested
- [ ] Error handling tested
- [ ] Performance acceptable

### 2. Monitoring

- [ ] Monitoring dashboards reviewed
- [ ] Alerts configured and tested
- [ ] Logs reviewed for errors
- [ ] Metrics baseline established

### 3. Communication

- [ ] Deployment announced to team
- [ ] Users notified of new feature
- [ ] Documentation shared
- [ ] Support team briefed

---

## Rollback Plan

In case of critical issues:

### 1. Immediate Actions

```bash
# Stop application
sudo systemctl stop pet-breeding-api

# Revert to previous version
git checkout <previous-commit>
poetry install

# Rollback database migrations
poetry run alembic downgrade -1

# Restart application
sudo systemctl start pet-breeding-api
```

### 2. Verification

- [ ] Application running on previous version
- [ ] Database rolled back successfully
- [ ] All services operational
- [ ] Users notified of rollback

---

## Sign-Off

### Development Team

- [ ] Code reviewed and approved
- [ ] Tests passing
- [ ] Documentation complete

**Signed:** _________________ Date: _________

### Operations Team

- [ ] Infrastructure ready
- [ ] Monitoring configured
- [ ] Backups configured

**Signed:** _________________ Date: _________

### Product Owner

- [ ] Feature tested and approved
- [ ] Ready for production

**Signed:** _________________ Date: _________

---

## Support Contacts

**Development Team:**
- Email: dev@yourdomain.com
- Slack: #dev-team

**Operations Team:**
- Email: ops@yourdomain.com
- Slack: #ops-team
- On-call: +1-XXX-XXX-XXXX

**Emergency Contacts:**
- Database Admin: +1-XXX-XXX-XXXX
- System Admin: +1-XXX-XXX-XXXX

---

**Deployment Date:** _________________

**Deployed By:** _________________

**Version:** _________________

**Notes:**
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
