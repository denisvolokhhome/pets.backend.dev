"""Signed-in users must not reach, change or see other users' data or accounts."""
import uuid
from datetime import date
from unittest.mock import patch

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breeding import Breeding
from app.models.breeding_pet import BreedingPet
from app.models.location import Location
from app.models.message import Message
from app.models.pet import Pet
from app.models.user import User

PRIVATE_PET_FIELDS = ("microchip", "vaccination", "health_certificate", "deworming",
                      "birth_certificate", "location_id")


def _user(email: str, **kw) -> User:
    kw.setdefault("is_verified", True)
    kw.setdefault("is_breeder", False)
    return User(email=email, name=email.split("@")[0],
                hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode(),
                is_active=True, **kw)


async def _login(client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    r = await client.post("/api/auth/jwt/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _add(session: AsyncSession, *objs):
    session.add_all(objs)
    await session.commit()
    for o in objs:
        await session.refresh(o)
    return objs


def _location(user: User, **kw) -> Location:
    defaults = dict(name="Home", address1="1 Main St", city="Austin", state="TX",
                    country="US", zipcode="78701", location_type="breeder", latitude=30.27, longitude=-97.74)
    defaults.update(kw)
    return Location(user_id=user.id, **defaults)


def _private_pet(owner: User, name: str, gender: str, location: Location | None = None) -> Pet:
    return Pet(user_id=owner.id, name=name, gender=gender, microchip="985112000000001",
               vaccination="Rabies 2026", health_certificate="Vet cert", deworming="Monthly",
               birth_certificate="BC-1", location_id=location.id if location else None)


@pytest.fixture
async def other_breeder(async_session: AsyncSession) -> User:
    (u,) = await _add(async_session, _user("victim-breeder@example.com", is_breeder=True,
                                           account_type="breeder"))
    return u


# ── 1. Litters: parents and puppies ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_assign_other_breeders_pets_as_parents(
        unauthenticated_client, async_session, test_breeder, test_breeding, other_breeder):
    sire, dam = await _add(async_session, _private_pet(other_breeder, "Sire", "Male"),
                           _private_pet(other_breeder, "Dam", "Female"))
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(f"/api/breedings/{test_breeding.id}/assign-pets",
                                          json={"pet_ids": [str(sire.id), str(dam.id)]}, headers=h)
    assert r.status_code == 400
    links = (await async_session.execute(
        select(BreedingPet).where(BreedingPet.breeding_id == test_breeding.id))).scalars().all()
    assert links == []


@pytest.mark.asyncio
async def test_cannot_assign_deleted_pets_as_parents(
        unauthenticated_client, async_session, test_breeder, test_breeding):
    sire, dam = await _add(async_session, _private_pet(test_breeder, "Sire", "Male"),
                           _private_pet(test_breeder, "Dam", "Female"))
    dam.is_deleted = True
    await async_session.commit()
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(f"/api/breedings/{test_breeding.id}/assign-pets",
                                          json={"pet_ids": [str(sire.id), str(dam.id)]}, headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_puppies_are_created_in_the_callers_account(
        unauthenticated_client, async_session, test_breeder, test_breeding, other_breeder):
    # A litter linked to another breeder's pets before the fix must not put puppies in their account.
    breeding_id, breeder_id = test_breeding.id, test_breeder.id
    sire, dam = await _add(async_session, _private_pet(other_breeder, "Sire", "Male"),
                           _private_pet(other_breeder, "Dam", "Female"))
    await _add(async_session, BreedingPet(breeding_id=breeding_id, pet_id=sire.id),
               BreedingPet(breeding_id=breeding_id, pet_id=dam.id))
    async_session.expire_all()
    h = await _login(unauthenticated_client, "breeder@example.com")
    r = await unauthenticated_client.post(
        f"/api/breedings/{breeding_id}/add-puppies",
        json={"puppies": [{"name": "Pup", "gender": "Male", "birth_date": "2026-11-01"}]}, headers=h)
    assert r.status_code == 200, r.text
    pup = (await async_session.execute(select(Pet).where(Pet.name == "Pup"))).scalar_one()
    assert pup.user_id == breeder_id
    assert pup.location_id is None  # never inherit another breeder's location


# ── 2. Pets: location and litter references ─────────────────────────────────

@pytest.mark.asyncio
async def test_create_pet_rejects_other_users_location(
        unauthenticated_client, async_session, test_breeder, other_breeder):
    (loc,) = await _add(async_session, _location(other_breeder, name="Secret kennel", is_published=False))
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post("/api/pets", json={"name": "Max", "location_id": loc.id}, headers=h)
    assert r.status_code == 400
    assert (await async_session.execute(select(Pet).where(Pet.name == "Max"))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_create_pet_rejects_other_users_breeding(
        unauthenticated_client, async_session, test_breeder, other_breeder):
    (theirs,) = await _add(async_session, Breeding(user_id=other_breeder.id, status="Started",
                                                   date_of_litter=date(2026, 1, 1)))
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post("/api/pets", json={"name": "Max", "breeding_id": theirs.id}, headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_update_pet_rejects_other_users_location_and_breeding(
        unauthenticated_client, async_session, test_breeder, other_breeder):
    (loc,) = await _add(async_session, _location(other_breeder))
    (theirs,) = await _add(async_session, Breeding(user_id=other_breeder.id, status="Started",
                                                   date_of_litter=date(2026, 1, 1)))
    (pet,) = await _add(async_session, Pet(user_id=test_breeder.id, name="Mine"))
    h = await _login(unauthenticated_client, test_breeder.email)
    r1 = await unauthenticated_client.put(f"/api/pets/{pet.id}", json={"location_id": loc.id}, headers=h)
    r2 = await unauthenticated_client.put(f"/api/pets/{pet.id}", json={"breeding_id": theirs.id}, headers=h)
    assert (r1.status_code, r2.status_code) == (400, 400)
    await async_session.refresh(pet)
    assert pet.location_id is None and pet.breeding_id is None


@pytest.mark.asyncio
async def test_pet_can_use_own_location_and_breeding(
        unauthenticated_client, async_session, test_breeder, test_breeding):
    (loc,) = await _add(async_session, _location(test_breeder))
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        "/api/pets", json={"name": "Max", "location_id": loc.id, "breeding_id": test_breeding.id}, headers=h)
    assert r.status_code == 201, r.text
    r = await unauthenticated_client.put(f"/api/pets/{r.json()['id']}", json={"location_id": None}, headers=h)
    assert r.status_code == 200


# ── 3. Password can only change with the current password ───────────────────

@pytest.mark.asyncio
async def test_stock_users_patch_cannot_change_password(unauthenticated_client, test_breeder):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.patch("/api/auth/users/me", json={"password": "Attacker123!"}, headers=h)
    assert r.status_code in (404, 405)
    await _login(unauthenticated_client, test_breeder.email)  # old password still works


@pytest.mark.asyncio
async def test_current_user_endpoint_still_works(unauthenticated_client, test_breeder):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.get("/api/auth/users/me", headers=h)
    assert r.status_code == 200
    assert r.json()["email"] == test_breeder.email
    assert "hashed_password" not in r.json()


# ── 4. Google sign-in cannot take over an account ───────────────────────────

def _google(email: str, verified: bool = True, oauth_id: str = "g-999"):
    from unittest.mock import AsyncMock, MagicMock

    from app.config import Settings
    settings = Settings(google_oauth_client_id="id", google_oauth_client_secret="secret",
                        google_oauth_redirect_uri="http://test/api/auth/google/callback")
    oauth = MagicMock()
    oauth.get_access_token = AsyncMock(return_value={"access_token": "tok"})
    userinfo = MagicMock()
    userinfo.json.return_value = {"email": email, "id": oauth_id, "verified_email": verified}
    http = MagicMock()
    http.get = AsyncMock(return_value=userinfo)
    http_cls = MagicMock()
    http_cls.return_value.__aenter__ = AsyncMock(return_value=http)
    http_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return settings, oauth, http_cls


async def _google_callback(client, email, verified=True):
    settings, oauth, http_cls = _google(email, verified)
    with patch("app.routers.auth.settings", settings), patch("app.routers.auth.google_oauth_client", oauth), \
            patch("httpx.AsyncClient", http_cls):
        return await client.get("/api/auth/google/callback?code=c", follow_redirects=False)


@pytest.mark.asyncio
async def test_google_unverified_email_is_refused(unauthenticated_client, async_session, test_pet_seeker):
    r = await _google_callback(unauthenticated_client, test_pet_seeker.email, verified=False)
    assert "token=" not in r.headers["location"]
    assert "error=" in r.headers["location"]


@pytest.mark.asyncio
async def test_google_sign_in_kills_squatters_password_on_unverified_account(
        unauthenticated_client, async_session):
    # Attacker registered the victim's email with their own password and never verified it.
    (squat,) = await _add(async_session, _user("victim@gmail.com", is_verified=False))
    r = await _google_callback(unauthenticated_client, "victim@gmail.com")
    assert "/auth/callback?token=" in r.headers["location"]

    login = await unauthenticated_client.post("/api/auth/jwt/login",
                                              data={"username": "victim@gmail.com", "password": "testpass123"})
    assert login.status_code == 400
    await async_session.refresh(squat)
    assert squat.is_verified and squat.oauth_provider == "google"


@pytest.mark.asyncio
async def test_google_sign_in_keeps_password_of_verified_account(unauthenticated_client, test_pet_seeker):
    r = await _google_callback(unauthenticated_client, test_pet_seeker.email)
    assert "/auth/callback?token=" in r.headers["location"]
    await _login(unauthenticated_client, test_pet_seeker.email)


# ── 5. Public pets endpoint hides private records ───────────────────────────

@pytest.mark.asyncio
async def test_public_breeder_pets_hide_private_fields(unauthenticated_client, async_session, other_breeder):
    (loc,) = await _add(async_session, _location(other_breeder))
    await _add(async_session, _private_pet(other_breeder, "Rex", "Male", loc))
    r = await unauthenticated_client.get(f"/api/pets/breeder/{other_breeder.id}")
    assert r.status_code == 200
    (pet,) = r.json()
    for f in PRIVATE_PET_FIELDS:
        assert pet[f] is None, f
    assert pet["name"] == "Rex"


@pytest.mark.asyncio
async def test_other_signed_in_user_sees_public_pet_fields_only(
        unauthenticated_client, async_session, test_breeder, other_breeder):
    await _add(async_session, _private_pet(other_breeder, "Rex", "Male"))
    h = await _login(unauthenticated_client, test_breeder.email)
    (pet,) = (await unauthenticated_client.get(f"/api/pets/breeder/{other_breeder.id}", headers=h)).json()
    assert pet["microchip"] is None


@pytest.mark.asyncio
async def test_public_breeder_pets_never_include_deleted(unauthenticated_client, async_session, other_breeder):
    (gone,) = await _add(async_session, _private_pet(other_breeder, "Gone", "Male"))
    gone.is_deleted = True
    await async_session.commit()
    r = await unauthenticated_client.get(f"/api/pets/breeder/{other_breeder.id}?include_deleted=true")
    assert r.json() == []


@pytest.mark.asyncio
async def test_owner_still_gets_full_pet_records(unauthenticated_client, async_session, test_breeder):
    (loc,) = await _add(async_session, _location(test_breeder))
    await _add(async_session, _private_pet(test_breeder, "Rex", "Male", loc))
    h = await _login(unauthenticated_client, test_breeder.email)
    (pet,) = (await unauthenticated_client.get(f"/api/pets/breeder/{test_breeder.id}", headers=h)).json()
    assert pet["microchip"] == "985112000000001"
    assert pet["location_id"] == loc.id


# ── 6. Public offspring hide the parents' private records ───────────────────

@pytest.fixture
async def offspring_with_parents(async_session, test_breeder, test_offspring):
    (loc,) = await _add(async_session, _location(test_breeder))
    sire, dam = await _add(async_session, _private_pet(test_breeder, "Sire", "Male", loc),
                           _private_pet(test_breeder, "Dam", "Female", loc))
    test_offspring.father_id, test_offspring.mother_id = sire.id, dam.id
    test_offspring.is_published = True
    await async_session.commit()
    offspring_id = test_offspring.id
    async_session.expire_all()
    return offspring_id


@pytest.mark.asyncio
async def test_public_offspring_hides_parent_private_fields(unauthenticated_client, offspring_with_parents):
    r = await unauthenticated_client.get(f"/api/offsprings/public/{offspring_with_parents}")
    assert r.status_code == 200, r.text
    body = r.json()
    for parent in ("father", "mother"):
        assert body[parent]["name"] in ("Sire", "Dam")
        for f in PRIVATE_PET_FIELDS:
            assert body[parent][f] is None, (parent, f)


@pytest.mark.asyncio
async def test_owner_offspring_detail_keeps_parent_fields(
        unauthenticated_client, test_breeder, offspring_with_parents):
    h = await _login(unauthenticated_client, "breeder@example.com")
    r = await unauthenticated_client.get(f"/api/offsprings/{offspring_with_parents}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["father"]["microchip"] == "985112000000001"


# ── 7. Provider public profile lists published locations only ───────────────

@pytest.mark.asyncio
async def test_provider_public_profile_hides_unpublished_locations(unauthenticated_client, async_session):
    (provider,) = await _add(async_session, _user(f"sp-{uuid.uuid4()}@example.com", account_type="service"))
    await _add(async_session, _location(provider, name="Shop", is_published=True),
               _location(provider, name="Home address", is_published=False))
    r = await unauthenticated_client.get(f"/api/services/provider/{provider.id}/public")
    assert r.status_code == 200, r.text
    assert [loc["name"] for loc in r.json()["locations"]] == ["Shop"]


# ── 9/10. Messages and reviews ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reply_cannot_forge_server_cards(unauthenticated_client, async_session, test_breeder, test_pet_seeker):
    (first,) = await _add(async_session, Message(sender_id=test_pet_seeker.id, receiver_id=test_breeder.id,
                                                 thread_id=uuid.uuid4(), content="Hi"))
    h = await _login(unauthenticated_client, test_breeder.email)
    forged = '{"__type": "location", "name": "Fake"}'
    r = await unauthenticated_client.post(f"/api/messages/{first.id}/respond",
                                          json={"response_text": forged}, headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_review_eligibility_requires_thread_participation(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker):
    (stranger,) = await _add(async_session, _user("stranger@example.com", account_type="pet_seeker"))
    thread = uuid.uuid4()
    await _add(async_session, Message(sender_id=test_pet_seeker.id, receiver_id=test_breeder.id,
                                      thread_id=thread, content="Hi"))
    h = await _login(unauthenticated_client, stranger.email)
    r = await unauthenticated_client.get(
        f"/api/reviews/eligibility?breeder_id={test_breeder.id}&thread_id={thread}", headers=h)
    assert r.status_code == 404
