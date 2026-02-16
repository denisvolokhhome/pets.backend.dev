"""
Script to geocode existing locations that don't have coordinates.

This script:
1. Finds all locations without coordinates
2. Geocodes them using the ZIP code
3. Updates the location with coordinates

Run with: python geocode_existing_locations.py
"""
import asyncio
import sys
from typing import Optional

from sqlalchemy import select

from app.database import get_async_session
from app.dependencies import settings
from app.models.location import Location
from app.services.geocoding_service import GeocodingService


async def geocode_location(
    location: Location,
    geocoding_service: GeocodingService
) -> bool:
    """
    Geocode a single location.
    
    Args:
        location: Location to geocode
        geocoding_service: Geocoding service instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Try geocoding by ZIP code
        coords = await geocoding_service.geocode_zip(location.zipcode)
        location.set_coordinates(coords.latitude, coords.longitude)
        print(f"✓ Geocoded: {location.name} ({location.city}, {location.state} {location.zipcode})")
        print(f"  Coordinates: {coords.latitude}, {coords.longitude}")
        return True
    except Exception as e:
        print(f"✗ Failed to geocode: {location.name} ({location.zipcode})")
        print(f"  Error: {e}")
        return False


async def main():
    """Main function to geocode all locations without coordinates."""
    print("=" * 80)
    print("Geocoding Existing Locations")
    print("=" * 80)
    print()
    
    # Initialize geocoding service
    geocoding_service = GeocodingService(settings, redis_client=None)
    
    success_count = 0
    failure_count = 0
    skipped_count = 0
    
    async for session in get_async_session():
        try:
            # Find all locations without coordinates
            query = select(Location).where(
                Location.coordinates.is_(None)
            )
            result = await session.execute(query)
            locations = result.scalars().all()
            
            total = len(locations)
            print(f"Found {total} location(s) without coordinates")
            print()
            
            if total == 0:
                print("All locations already have coordinates!")
                return
            
            # Geocode each location
            for i, location in enumerate(locations, 1):
                print(f"[{i}/{total}] Processing: {location.name}")
                
                # Skip if no ZIP code
                if not location.zipcode:
                    print(f"  ⚠ Skipped: No ZIP code")
                    skipped_count += 1
                    continue
                
                # Geocode
                success = await geocode_location(location, geocoding_service)
                
                if success:
                    success_count += 1
                    # Commit after each successful geocode
                    await session.commit()
                else:
                    failure_count += 1
                
                print()
                
                # Add delay to respect rate limits
                if i < total:
                    await asyncio.sleep(1.1)  # 1 request per second + buffer
            
            # Summary
            print("=" * 80)
            print("Summary")
            print("=" * 80)
            print(f"Total locations processed: {total}")
            print(f"✓ Successfully geocoded: {success_count}")
            print(f"✗ Failed to geocode: {failure_count}")
            print(f"⚠ Skipped (no ZIP): {skipped_count}")
            print()
            
            if success_count > 0:
                print("✓ Locations have been updated with coordinates!")
                print("  They should now appear in map searches.")
            
            if failure_count > 0:
                print()
                print("⚠ Some locations could not be geocoded.")
                print("  These locations will not appear in map searches until geocoded.")
                print("  You can manually edit and save them in the UI to trigger geocoding.")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            break


if __name__ == "__main__":
    asyncio.run(main())

