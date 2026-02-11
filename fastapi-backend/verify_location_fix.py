"""
Verify that the location fix was successful.
"""
import asyncio
from sqlalchemy import select, text

from app.database import get_async_session
from app.models.location import Location


async def main():
    """Verify location has been fixed."""
    print("=" * 80)
    print("Verifying Location Fix for ZIP 21704")
    print("=" * 80)
    print()
    
    async for session in get_async_session():
        try:
            # Check location with ZIP 21704
            query = select(Location).where(Location.zipcode == '21704')
            result = await session.execute(query)
            locations = result.scalars().all()
            
            if not locations:
                print("❌ No locations found with ZIP 21704")
                return
            
            for loc in locations:
                print(f"Location: {loc.name}")
                print(f"Address: {loc.address1}, {loc.city}, {loc.state} {loc.zipcode}")
                print(f"Published: {'✅ Yes' if loc.is_published else '❌ No'}")
                print(f"Coordinates: {'✅ Set' if loc.coordinates else '❌ Missing'}")
                if loc.latitude and loc.longitude:
                    print(f"  Latitude: {loc.latitude}")
                    print(f"  Longitude: {loc.longitude}")
                print(f"Location Type: {loc.location_type}")
                print()
                
                # Check if location has pets
                from app.models.pet import Pet
                pet_query = select(Pet).where(
                    Pet.location_id == loc.id,
                    Pet.is_deleted == False
                )
                pet_result = await session.execute(pet_query)
                pets = pet_result.scalars().all()
                
                print(f"Pets at location: {len(pets)}")
                for pet in pets:
                    print(f"  - {pet.name} (Breed ID: {pet.breed_id})")
                print()
            
            # Check if location would appear in search
            print("=" * 80)
            print("Search Eligibility Check")
            print("=" * 80)
            print()
            
            for loc in locations:
                eligible = True
                reasons = []
                
                if not loc.is_published:
                    eligible = False
                    reasons.append("❌ Not published")
                else:
                    reasons.append("✅ Published")
                
                if not loc.coordinates:
                    eligible = False
                    reasons.append("❌ No coordinates")
                else:
                    reasons.append("✅ Has coordinates")
                
                if loc.location_type != 'user':
                    eligible = False
                    reasons.append(f"❌ Wrong type ({loc.location_type})")
                else:
                    reasons.append("✅ Correct type (user)")
                
                # Check pets
                pet_query = select(Pet).where(
                    Pet.location_id == loc.id,
                    Pet.is_deleted == False,
                    Pet.breed_id.isnot(None)
                )
                pet_result = await session.execute(pet_query)
                pets_with_breeds = pet_result.scalars().all()
                
                if len(pets_with_breeds) == 0:
                    eligible = False
                    reasons.append("❌ No pets with breeds")
                else:
                    reasons.append(f"✅ Has {len(pets_with_breeds)} pet(s) with breeds")
                
                print(f"Location: {loc.name}")
                for reason in reasons:
                    print(f"  {reason}")
                print()
                
                if eligible:
                    print("✅ This location WILL appear in map searches!")
                else:
                    print("⚠️  This location will NOT appear in map searches yet.")
                    print("   Fix the issues above to make it visible.")
                print()
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            break


if __name__ == "__main__":
    asyncio.run(main())
