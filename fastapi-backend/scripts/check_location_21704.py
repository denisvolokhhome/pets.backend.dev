#!/usr/bin/env python3
"""Check recent locations and their geocoding status."""
import asyncio
import sys
sys.path.insert(0, 'pets.backend.dev/fastapi-backend')

from sqlalchemy import select
from app.db import get_async_session
from app.models.location import Location

async def check_locations():
    async for session in get_async_session():
        # Get the most recent locations
        result = await session.execute(
            select(Location)
            .order_by(Location.created_at.desc())
            .limit(5)
        )
        locations = result.scalars().all()
        
        print('Recent locations:')
        print('=' * 80)
        for loc in locations:
            print(f'ID: {loc.id}')
            print(f'Name: {loc.name}')
            print(f'Address: {loc.address1}, {loc.city}, {loc.state} {loc.zipcode}')
            print(f'Coordinates: lat={loc.latitude}, lon={loc.longitude}')
            print(f'Published: {loc.is_published}')
            print(f'Created: {loc.created_at}')
            
            # Check if geocoded
            if loc.latitude is None or loc.longitude is None:
                print('⚠️  NOT GEOCODED - This location will not appear on the map!')
            else:
                print('✓ Geocoded successfully')
            print('=' * 80)
        break

if __name__ == '__main__':
    asyncio.run(check_locations())
