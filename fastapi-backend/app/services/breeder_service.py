"""Breeder service for geospatial search of breeding locations."""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from app.models.location import Location
from app.models.user import User
from app.models.pet import Pet
from app.models.breed import Breed
from app.models.breeder_review import BreederReview
from app.schemas.breeder import BreederSearchResult, BreedInfo


class BreederService:
    """Service for searching breeding locations with geospatial queries."""
    
    async def search_nearby_breeding_locations(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        radius_miles: float,
        breed_id: Optional[int] = None,
        animal_kind: Optional[str] = None
    ) -> List[BreederSearchResult]:
        """
        Search for breeding locations within radius using PostGIS.
        
        This method finds breeding locations (from locations table with location_type='user')
        that have pets within the specified radius. Each location can have multiple breeds
        based on the pets assigned to that location via pets.location_id.
        
        Args:
            db: Database session
            latitude: Search center latitude (-90 to 90)
            longitude: Search center longitude (-180 to 180)
            radius_miles: Search radius in miles (> 0)
            breed_id: Optional breed filter - only return locations with this breed
        
        Returns:
            List of BreederSearchResult with location details and available breeds
        
        Algorithm:
        1. Create point geometry from search coordinates
        2. Convert radius from miles to meters (1 mile = 1609.34 meters)
        3. Use ST_DWithin for efficient spatial filtering on locations table
        4. Join with pets table to get available breeds at each location
        5. Filter by breed_id if specified (pets.breed_id = breed_id)
        6. Calculate exact distance using ST_Distance with spheroid
        7. Group by location to aggregate available breeds
        8. Order by distance ascending
        9. Return results with location details and available breeds
        """
        # Create search point geometry
        search_point = func.ST_SetSRID(
            func.ST_MakePoint(longitude, latitude),
            4326  # WGS84 coordinate system (standard for GPS coordinates)
        )
        
        # Convert miles to meters for PostGIS distance functions
        radius_meters = radius_miles * 1609.34
        
        # Subquery for review aggregation per breeder
        review_subq = (
            select(
                BreederReview.breeder_id,
                func.round(func.coalesce(func.avg(BreederReview.rating), 0), 1).label('avg_rating'),
                func.count(BreederReview.id).label('review_count'),
            )
            .group_by(BreederReview.breeder_id)
            .subquery()
        )

        # Build base query for locations with pets
        # We need to find locations that:
        # 1. Are user locations (location_type='user')
        # 2. Have coordinates set
        # 3. Belong to active users
        # 4. Have at least one pet with a breed assigned
        # 5. Are within the search radius
        query = (
            select(
                Location.id.label('location_id'),
                Location.user_id.label('user_id'),
                User.breedery_name.label('breeder_name'),
                func.ST_Y(Location.coordinates).label('latitude'),
                func.ST_X(Location.coordinates).label('longitude'),
                (func.ST_Distance(
                    Location.coordinates,
                    search_point,
                    True  # Use spheroid for accurate distance calculation
                ) / 1609.34).label('distance'),  # Convert meters to miles
                User.profile_image_path.label('thumbnail_url'),
                Location.name.label('location_description'),
                func.coalesce(review_subq.c.avg_rating, 0).label('rating'),
                func.coalesce(review_subq.c.review_count, 0).label('review_count'),
            )
            .join(User, Location.user_id == User.id)
            .join(Pet, Pet.location_id == Location.id)
            .outerjoin(review_subq, review_subq.c.breeder_id == Location.user_id)
            .where(
                Location.location_type == 'user',  # Only breeding locations
                Location.is_published == True,  # Only published locations visible on map
                Location.coordinates.isnot(None),  # Must have coordinates
                User.is_active == True,  # Only active breeders
                Pet.is_deleted == False,  # Exclude deleted pets
                Pet.breed_id.isnot(None),  # Only pets with breed assigned
                func.ST_DWithin(
                    Location.coordinates,
                    search_point,
                    radius_meters,
                    True  # Use spheroid for accurate filtering
                )
            )
        )
        
        # Filter by breed if specified
        if breed_id:
            query = query.where(Pet.breed_id == breed_id)
        
        # Filter by animal kind if specified
        if animal_kind:
            query = query.join(Breed, Pet.breed_id == Breed.id).where(Breed.kind == animal_kind)
        
        # Group by location to avoid duplicates (one row per location)
        query = query.group_by(
            Location.id,
            Location.user_id,
            User.breedery_name,
            Location.coordinates,
            User.profile_image_path,
            Location.name,
            review_subq.c.avg_rating,
            review_subq.c.review_count,
        )
        
        # Order by distance (nearest first)
        query = query.order_by('distance')
        
        # Execute query to get locations
        result = await db.execute(query)
        location_results = result.all()
        
        # For each location, get available breeds
        results = []
        for loc in location_results:
            # Query breeds available at this location
            breeds_query = (
                select(
                    Breed.id.label('breed_id'),
                    Breed.name.label('breed_name'),
                    Breed.kind.label('breed_kind'),
                    func.count(Pet.id).label('pet_count')
                )
                .join(Pet, Pet.breed_id == Breed.id)
                .where(
                    Pet.location_id == loc.location_id,
                    Pet.is_deleted == False,
                    Pet.breed_id.isnot(None)
                )
                .group_by(Breed.id, Breed.name, Breed.kind)
            )
            
            # If breed filter is specified, only include that breed
            if breed_id:
                breeds_query = breeds_query.where(Breed.id == breed_id)
            
            breeds_result = await db.execute(breeds_query)
            available_breeds = breeds_result.all()
            
            # Build result object
            results.append(BreederSearchResult(
                location_id=loc.location_id,
                user_id=loc.user_id,
                breeder_name=loc.breeder_name or "Breeder, who didn't named himself",
                latitude=loc.latitude,
                longitude=loc.longitude,
                distance=round(loc.distance, 1),  # Round to 1 decimal place
                available_breeds=[
                    BreedInfo(
                        breed_id=b.breed_id,
                        breed_name=b.breed_name,
                        breed_kind=b.breed_kind,
                        pet_count=b.pet_count
                    ) for b in available_breeds
                ],
                thumbnail_url=loc.thumbnail_url,
                location_description=loc.location_description,
                rating=float(loc.rating) if loc.rating else None,
                review_count=int(loc.review_count) if loc.review_count else 0,
            ))
        
        return results


# Singleton instance
breeder_service = BreederService()
