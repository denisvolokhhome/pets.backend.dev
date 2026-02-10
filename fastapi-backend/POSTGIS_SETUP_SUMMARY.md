# PostGIS Setup Summary

## Overview

This document summarizes the PostGIS setup for the Pet Search with Map feature. PostGIS has been integrated into the FastAPI backend to enable efficient geospatial queries for breeder location searches.

## Changes Made

### 1. Dependencies Added

Added to `requirements.txt`:
- `geoalchemy2>=0.15.0` - SQLAlchemy extension for PostGIS
- `shapely>=2.0.0` - Geometric object manipulation library

### 2. Database Migration

Created Alembic migration: `26d077d96d3a_add_postgis_geometry_to_locations.py`

**Migration Actions:**
- Enables PostGIS extension in PostgreSQL
- Adds `latitude` and `longitude` columns to `locations` table (if not exists)
- Adds `coordinates` geometry column (POINT type with SRID 4326 - WGS84)
- Creates GIST spatial index on `coordinates` column for performance

**SQL Generated:**
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
ALTER TABLE locations ADD COLUMN latitude FLOAT;
ALTER TABLE locations ADD COLUMN longitude FLOAT;
ALTER TABLE locations ADD COLUMN coordinates geometry(POINT,4326);
CREATE INDEX idx_locations_coordinates ON locations USING gist (coordinates);
```

### 3. Location Model Updates

Updated `app/models/location.py` with:

**New Fields:**
- `latitude: Mapped[Optional[float]]` - Latitude coordinate
- `longitude: Mapped[Optional[float]]` - Longitude coordinate  
- `coordinates: Mapped[Optional[Point]]` - PostGIS geometry column

**New Properties:**
- `lat` - Returns latitude from geometry or latitude field
- `lon` - Returns longitude from geometry or longitude field

**New Methods:**
- `set_coordinates(latitude, longitude)` - Sets both lat/lon fields and geometry column
- `get_coordinates_tuple()` - Returns (latitude, longitude) tuple or None

**Benefits:**
- Backward compatibility with existing lat/lon fields
- Efficient spatial queries using PostGIS functions
- Automatic GIST index for fast distance calculations

### 4. Tests Added

Created `tests/unit/test_location_geometry.py` with 5 unit tests:
- `test_location_set_coordinates` - Verifies coordinate setting
- `test_location_lat_property` - Tests latitude property
- `test_location_lon_property` - Tests longitude property
- `test_location_get_coordinates_tuple` - Tests tuple conversion
- `test_location_repr_with_coordinates` - Tests string representation

**All tests pass ✓**

## Usage Examples

### Setting Coordinates

```python
from app.models.location import Location

location = Location(
    name="Breeder Location",
    address1="123 Main St",
    city="San Francisco",
    state="CA",
    country="USA",
    zipcode="94102",
    location_type="user"
)

# Set coordinates (updates both lat/lon and geometry)
location.set_coordinates(37.7749, -122.4194)
```

### Accessing Coordinates

```python
# Get individual coordinates
lat = location.lat  # 37.7749
lon = location.lon  # -122.4194

# Get as tuple
coords = location.get_coordinates_tuple()  # (37.7749, -122.4194)
```

### Spatial Queries (Future Use)

The geometry column enables efficient PostGIS queries:

```python
from sqlalchemy import func

# Find locations within radius (using ST_DWithin)
search_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
radius_meters = 10 * 1609.34  # 10 miles to meters

query = db.query(Location).filter(
    func.ST_DWithin(
        Location.coordinates,
        search_point,
        radius_meters,
        True  # Use spheroid for accuracy
    )
)

# Calculate distances (using ST_Distance)
distance = func.ST_Distance(
    Location.coordinates,
    search_point,
    True  # Use spheroid
) / 1609.34  # Convert to miles
```

## Next Steps

To apply this migration to your database:

1. Ensure PostgreSQL with PostGIS is installed
2. Run the migration:
   ```bash
   ./venv/bin/alembic upgrade head
   ```

3. Verify PostGIS is enabled:
   ```sql
   SELECT PostGIS_version();
   ```

## Requirements Validated

This implementation satisfies:
- **Requirement 7.2**: Haversine distance calculation support via PostGIS ST_Distance
- **Requirement 13.2**: Database schema with spatial indexing for efficient queries

## Technical Notes

- **SRID 4326**: WGS84 coordinate system (standard for GPS coordinates)
- **GIST Index**: Generalized Search Tree index optimized for spatial data
- **Spheroid Calculations**: Uses Earth's actual shape for accurate distances
- **Backward Compatibility**: Maintains separate lat/lon columns for existing code
