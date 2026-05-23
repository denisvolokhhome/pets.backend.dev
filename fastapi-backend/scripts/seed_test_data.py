"""
Seed test data: 3 breeders with pets/locations and 3 service providers with services.
For development/testing purposes only. Safe to run multiple times (idempotent).

Usage:
    cd pets.backend.dev/fastapi-backend
    source venv/bin/activate
    PYTHONPATH=. python scripts/seed_test_data.py
"""
import asyncio
import uuid
from decimal import Decimal

from fastapi_users.password import PasswordHelper
from sqlalchemy import select, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session_maker
from app.models.user import User
from app.models.location import Location
from app.models.breed import Breed
from app.models.pet import Pet
from app.models.service import Service, service_locations
from app.models.service_category import ServiceCategory, user_service_categories

PASSWORD = "Test1234!"
password_helper = PasswordHelper()
HASHED_PASSWORD = password_helper.hash(PASSWORD)


# ── Breeder seed data ─────────────────────────────────────────────────────────

BREEDERS = [
    {
        "email": "john.golden@breedly.test",
        "name": "John Golden",
        "breedery_name": "Golden Paws Kennel",
        "breedery_description": "Award-winning Golden Retriever breeder with 15 years of experience. Health-tested, family-raised puppies.",
        "is_breeder": True,
        "account_type": "breeder",
        "location": {
            "name": "Golden Paws Kennel",
            "address1": "1234 Rosemont Avenue",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21701",
            "location_type": "user",
            "is_published": True,
            "is_default": True,
        },
        "pets": [
            {
                "name": "Max",
                "gender": "Male",
                "breed_name": "Golden Retriever",
                "description": "Champion bloodline Golden Retriever, health-tested OFA hips/elbows.",
            },
            {
                "name": "Bella",
                "gender": "Female",
                "breed_name": "Golden Retriever",
                "description": "Beautiful female Golden, excellent temperament, great with children.",
            },
        ],
    },
    {
        "email": "maria.siamese@breedly.test",
        "name": "Maria Chen",
        "breedery_name": "Silk Road Cattery",
        "breedery_description": "Specialising in Siamese and Burmese cats. TICA registered cattery, all kittens come with health guarantee.",
        "is_breeder": True,
        "account_type": "breeder",
        "location": {
            "name": "Silk Road Cattery",
            "address1": "88 West Patrick Street",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21701",
            "location_type": "user",
            "is_published": True,
            "is_default": True,
        },
        "pets": [
            {
                "name": "Luna",
                "gender": "Female",
                "breed_name": "Siamese",
                "description": "Traditional Siamese female, stunning blue eyes, very vocal and affectionate.",
            },
            {
                "name": "Shadow",
                "gender": "Male",
                "breed_name": "Burmese",
                "description": "Sable Burmese male, playful and dog-like personality.",
            },
        ],
    },
    {
        "email": "tom.labrador@breedly.test",
        "name": "Tom Bradley",
        "breedery_name": "Blue Ridge Labs",
        "breedery_description": "English Labrador Retrievers bred for health, temperament and conformation. AKC registered.",
        "is_breeder": True,
        "account_type": "breeder",
        "location": {
            "name": "Blue Ridge Labs",
            "address1": "500 Shookstown Road",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21702",
            "location_type": "user",
            "is_published": True,
            "is_default": True,
        },
        "pets": [
            {
                "name": "Duke",
                "gender": "Male",
                "breed_name": "Labrador Retriever",
                "description": "Yellow English Lab, calm temperament, excellent for families.",
            },
            {
                "name": "Rosie",
                "gender": "Female",
                "breed_name": "Labrador Retriever",
                "description": "Chocolate Lab female, loves water, great hunting companion.",
            },
        ],
    },
]


# ── Service provider seed data ────────────────────────────────────────────────

SERVICE_PROVIDERS = [
    {
        "email": "amy.groomer@breedly.test",
        "name": "Amy Wilson",
        "breedery_description": "Professional pet groomer with 8 years of experience. Mobile grooming available.",
        "account_type": "service",
        "categories": ["grooming", "pet-sitting"],
        "location": {
            "name": "Amy's Mobile Grooming",
            "address1": "210 North Market Street",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21701",
            "location_type": "service",
            "is_published": True,
            "is_default": True,
        },
        "services": [
            {
                "category_slug": "grooming",
                "title": "Full Dog Grooming",
                "description": "Bath, blow-dry, haircut, nail trim, ear cleaning and teeth brushing. All breeds welcome.",
                "price_from": Decimal("45.00"),
                "price_to": Decimal("95.00"),
                "price_unit": "per_session",
            },
            {
                "category_slug": "grooming",
                "title": "Cat Grooming & De-shedding",
                "description": "Gentle cat grooming including bath, blow-dry, brush-out and nail trim.",
                "price_from": Decimal("55.00"),
                "price_to": Decimal("75.00"),
                "price_unit": "per_session",
            },
            {
                "category_slug": "pet-sitting",
                "title": "In-Home Pet Sitting",
                "description": "I come to your home to feed, play and care for your pets while you're away.",
                "price_from": Decimal("25.00"),
                "price_to": Decimal("35.00"),
                "price_unit": "per_visit",
            },
        ],
    },
    {
        "email": "carlos.walker@breedly.test",
        "name": "Carlos Rivera",
        "breedery_description": "Certified dog trainer and professional dog walker. Serving the Frederick area.",
        "account_type": "service",
        "categories": ["dog-walking", "pet-training"],
        "location": {
            "name": "Carlos Dog Services",
            "address1": "125 East Church Street",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21701",
            "location_type": "service",
            "is_published": True,
            "is_default": True,
        },
        "services": [
            {
                "category_slug": "dog-walking",
                "title": "30-Minute Dog Walk",
                "description": "Solo or small group walks in your neighbourhood. GPS tracked, photo updates sent.",
                "price_from": Decimal("18.00"),
                "price_to": Decimal("22.00"),
                "price_unit": "per_visit",
            },
            {
                "category_slug": "dog-walking",
                "title": "60-Minute Adventure Walk",
                "description": "Extended walk including off-leash time at a local dog park.",
                "price_from": Decimal("30.00"),
                "price_to": Decimal("35.00"),
                "price_unit": "per_visit",
            },
            {
                "category_slug": "pet-training",
                "title": "Basic Obedience Training",
                "description": "Sit, stay, come, heel and leash manners. Positive reinforcement methods only.",
                "price_from": Decimal("60.00"),
                "price_to": Decimal("80.00"),
                "price_unit": "per_session",
            },
        ],
    },
    {
        "email": "lisa.boarding@breedly.test",
        "name": "Lisa Park",
        "breedery_description": "Luxury pet boarding and daycare in a home environment. Small groups, lots of love.",
        "account_type": "service",
        "categories": ["pet-boarding", "pet-daycare", "cat-sitting"],
        "location": {
            "name": "Lisa's Pet Haven",
            "address1": "77 Willowdale Drive",
            "city": "Frederick",
            "state": "MD",
            "country": "USA",
            "zipcode": "21703",
            "location_type": "service",
            "is_published": True,
            "is_default": True,
        },
        "services": [
            {
                "category_slug": "pet-boarding",
                "title": "Overnight Dog Boarding",
                "description": "Your dog stays in my home, sleeps on the couch, gets walks and playtime. Max 3 dogs at a time.",
                "price_from": Decimal("55.00"),
                "price_to": Decimal("70.00"),
                "price_unit": "per_day",
            },
            {
                "category_slug": "pet-daycare",
                "title": "Dog Daycare",
                "description": "Full day of play, socialisation and rest. Drop off 7am, pick up by 7pm.",
                "price_from": Decimal("35.00"),
                "price_to": Decimal("45.00"),
                "price_unit": "per_day",
            },
            {
                "category_slug": "cat-sitting",
                "title": "Cat Boarding",
                "description": "Quiet, calm space for your cat. Separate from dogs. Daily photos and updates.",
                "price_from": Decimal("30.00"),
                "price_to": Decimal("40.00"),
                "price_unit": "per_day",
            },
        ],
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_or_create_user(session, email: str, name: str, is_breeder: bool,
                              account_type: str, breedery_name: str = None,
                              breedery_description: str = None) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        print(f"  ↩  User already exists: {email}")
        return user

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=HASHED_PASSWORD,
        name=name,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=is_breeder,
        account_type=account_type,
        breedery_name=breedery_name,
        breedery_description=breedery_description,
    )
    session.add(user)
    await session.flush()
    print(f"  ✓  Created user: {email}")
    return user


async def get_or_create_location(session, user_id, loc_data: dict) -> Location:
    result = await session.execute(
        select(Location).where(
            Location.user_id == user_id,
            Location.name == loc_data["name"],
        )
    )
    loc = result.scalar_one_or_none()
    if loc:
        # Update address to new Frederick location
        loc.address1 = loc_data["address1"]
        loc.city = loc_data["city"]
        loc.state = loc_data["state"]
        loc.country = loc_data["country"]
        loc.zipcode = loc_data["zipcode"]
        loc.location_type = loc_data.get("location_type", "user")
        await session.flush()
        return loc

    loc = Location(
        user_id=user_id,
        name=loc_data["name"],
        address1=loc_data["address1"],
        city=loc_data["city"],
        state=loc_data["state"],
        country=loc_data["country"],
        zipcode=loc_data["zipcode"],
        location_type=loc_data.get("location_type", "user"),
        is_published=loc_data.get("is_published", True),
        is_default=loc_data.get("is_default", True),
    )
    session.add(loc)
    await session.flush()
    return loc


async def get_breed_id(session, breed_name: str) -> int | None:
    result = await session.execute(
        select(Breed.id).where(Breed.name.ilike(f"%{breed_name}%"))
    )
    row = result.first()
    return row[0] if row else None


async def get_category_id(session, slug: str) -> int | None:
    result = await session.execute(
        select(ServiceCategory.id).where(ServiceCategory.slug == slug)
    )
    row = result.first()
    return row[0] if row else None


# ── Main seed ─────────────────────────────────────────────────────────────────

async def seed():
    async with async_session_maker() as session:
        print("\n" + "=" * 60)
        print("Seeding test breeders")
        print("=" * 60)

        for b in BREEDERS:
            print(f"\n→ {b['name']} ({b['email']})")
            user = await get_or_create_user(
                session,
                email=b["email"],
                name=b["name"],
                is_breeder=True,
                account_type="breeder",
                breedery_name=b.get("breedery_name"),
                breedery_description=b.get("breedery_description"),
            )

            loc = await get_or_create_location(session, user.id, b["location"])

            for pet_data in b.get("pets", []):
                # Check if pet already exists
                existing = await session.execute(
                    select(Pet).where(Pet.user_id == user.id, Pet.name == pet_data["name"])
                )
                if existing.scalar_one_or_none():
                    print(f"  ↩  Pet already exists: {pet_data['name']}")
                    continue

                breed_id = await get_breed_id(session, pet_data["breed_name"])
                if not breed_id:
                    print(f"  ⚠  Breed not found: {pet_data['breed_name']}, skipping pet")
                    continue

                pet = Pet(
                    user_id=user.id,
                    breed_id=breed_id,
                    location_id=loc.id,
                    name=pet_data["name"],
                    gender=pet_data["gender"],
                    description=pet_data.get("description"),
                    is_deleted=False,
                )
                session.add(pet)
                print(f"  ✓  Created pet: {pet_data['name']} ({pet_data['breed_name']})")

        await session.commit()

        print("\n" + "=" * 60)
        print("Seeding test service providers")
        print("=" * 60)

        for sp in SERVICE_PROVIDERS:
            print(f"\n→ {sp['name']} ({sp['email']})")
            user = await get_or_create_user(
                session,
                email=sp["email"],
                name=sp["name"],
                is_breeder=False,
                account_type="service",
                breedery_description=sp.get("breedery_description"),
            )

            # Associate categories
            for slug in sp.get("categories", []):
                cat_id = await get_category_id(session, slug)
                if not cat_id:
                    print(f"  ⚠  Category not found: {slug}")
                    continue
                # Insert if not exists
                await session.execute(
                    text("""
                        INSERT INTO user_service_categories (user_id, category_id)
                        VALUES (:uid, :cid)
                        ON CONFLICT DO NOTHING
                    """),
                    {"uid": user.id, "cid": cat_id},
                )
                print(f"  ✓  Category: {slug}")

            loc = await get_or_create_location(session, user.id, sp["location"])

            for svc_data in sp.get("services", []):
                # Check if service already exists
                existing = await session.execute(
                    select(Service).where(
                        Service.user_id == user.id,
                        Service.title == svc_data["title"],
                        Service.is_deleted == False,
                    )
                )
                if existing.scalar_one_or_none():
                    print(f"  ↩  Service already exists: {svc_data['title']}")
                    continue

                cat_id = await get_category_id(session, svc_data["category_slug"])
                if not cat_id:
                    print(f"  ⚠  Category not found: {svc_data['category_slug']}")
                    continue

                svc = Service(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    category_id=cat_id,
                    title=svc_data["title"],
                    description=svc_data.get("description"),
                    price_from=svc_data.get("price_from"),
                    price_to=svc_data.get("price_to"),
                    price_unit=svc_data.get("price_unit"),
                    is_active=True,
                    is_deleted=False,
                )
                session.add(svc)
                await session.flush()

                # Link service to location
                await session.execute(
                    text("""
                        INSERT INTO service_locations (service_id, location_id)
                        VALUES (:sid, :lid)
                        ON CONFLICT DO NOTHING
                    """),
                    {"sid": svc.id, "lid": loc.id},
                )
                print(f"  ✓  Service: {svc_data['title']}")

        await session.commit()

        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        breeders_count = await session.execute(
            text("SELECT COUNT(*) FROM users WHERE account_type = 'breeder'")
        )
        sp_count = await session.execute(
            text("SELECT COUNT(*) FROM users WHERE account_type = 'service'")
        )
        pets_count = await session.execute(
            text("SELECT COUNT(*) FROM pets WHERE is_deleted = false")
        )
        services_count = await session.execute(
            text("SELECT COUNT(*) FROM services WHERE is_deleted = false")
        )
        print(f"  Breeders:          {breeders_count.scalar()}")
        print(f"  Service providers: {sp_count.scalar()}")
        print(f"  Pets:              {pets_count.scalar()}")
        print(f"  Services:          {services_count.scalar()}")
        print()
        print(f"  All test accounts use password: {PASSWORD}")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
