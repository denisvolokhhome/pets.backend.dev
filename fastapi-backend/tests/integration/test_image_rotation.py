"""Rotating stored pet / offspring / profile images, and EXIF orientation on upload."""
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.models.pet import Pet

STORAGE_ROOT = Path(Settings().storage_path).parent


def _jpeg(width=200, height=100, orientation=None) -> BytesIO:
    img = Image.new("RGB", (width, height), "blue")
    img.paste((255, 0, 0), (0, 0, 20, 20))  # red marker, top-left
    buf = BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    buf.seek(0)
    return buf


def _size(rel_path: str):
    with Image.open(STORAGE_ROOT / rel_path) as im:
        return im.size


async def _login(client, email):
    r = await client.post("/api/auth/jwt/login", data={"username": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def breeder_pet(async_session, test_breeder) -> Pet:
    pet = Pet(user_id=test_breeder.id, name="Rex")
    async_session.add(pet)
    await async_session.commit()
    await async_session.refresh(pet)
    return pet


async def _upload_pet_image(client, h, pet_id, buf):
    r = await client.post(
        f"/api/pets/{pet_id}/image", files={"file": ("p.jpg", buf, "image/jpeg")}, headers=h
    )
    assert r.status_code == 200, r.text
    return r.json()["images"][-1]


@pytest.mark.asyncio
async def test_rotate_pet_image_clockwise(unauthenticated_client, test_breeder, breeder_pet):
    h = await _login(unauthenticated_client, test_breeder.email)
    img = await _upload_pet_image(unauthenticated_client, h, breeder_pet.id, _jpeg())
    old = img["image_path"]
    assert _size(old) == (200, 100)

    r = await unauthenticated_client.post(
        f"/api/pets/{breeder_pet.id}/image/{img['id']}/rotate", json={"degrees": 90}, headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()
    new = body["images"][0]["image_path"]
    assert new != old  # new file name busts browser caches
    assert not (STORAGE_ROOT / old).exists()
    assert _size(new) == (100, 200)
    assert body["image_path"] == new  # legacy primary field follows
    # Clockwise: the top-left marker ends up top-right.
    with Image.open(STORAGE_ROOT / new) as im:
        r_, g_, b_ = im.convert("RGB").getpixel((95, 5))
    assert r_ > 200 and b_ < 80


@pytest.mark.asyncio
async def test_rotate_rejects_odd_angles(unauthenticated_client, test_breeder, breeder_pet):
    h = await _login(unauthenticated_client, test_breeder.email)
    img = await _upload_pet_image(unauthenticated_client, h, breeder_pet.id, _jpeg())
    r = await unauthenticated_client.post(
        f"/api/pets/{breeder_pet.id}/image/{img['id']}/rotate", json={"degrees": 45}, headers=h
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_rotate_someone_elses_pet_image(
    unauthenticated_client, async_session, test_breeder, breeder_pet
):
    import bcrypt

    from app.models.user import User

    other = User(
        email="other-breeder@example.com", is_active=True, is_verified=True, is_breeder=True,
        hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode(),
    )
    async_session.add(other)
    await async_session.commit()

    h = await _login(unauthenticated_client, test_breeder.email)
    img = await _upload_pet_image(unauthenticated_client, h, breeder_pet.id, _jpeg())
    h2 = await _login(unauthenticated_client, other.email)
    r = await unauthenticated_client.post(
        f"/api/pets/{breeder_pet.id}/image/{img['id']}/rotate", json={"degrees": 90}, headers=h2
    )
    assert r.status_code == 404
    assert (STORAGE_ROOT / img["image_path"]).exists()


@pytest.mark.asyncio
async def test_rotate_offspring_image(unauthenticated_client, test_breeder, test_offspring):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        f"/api/offsprings/{test_offspring.id}/images",
        files={"file": ("o.jpg", _jpeg(), "image/jpeg")}, headers=h,
    )
    assert r.status_code == 201, r.text
    img = r.json()
    r = await unauthenticated_client.post(
        f"/api/offsprings/{test_offspring.id}/images/{img['id']}/rotate",
        json={"degrees": -90}, headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["image_path"] != img["image_path"]
    assert _size(r.json()["image_path"]) == (100, 200)


@pytest.mark.asyncio
async def test_rotate_profile_image(unauthenticated_client, test_breeder):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        "/api/users/me/profile-image", files={"file": ("a.jpg", _jpeg(), "image/jpeg")}, headers=h
    )
    assert r.status_code == 200, r.text
    old = r.json()["profile_image_path"]
    r = await unauthenticated_client.post(
        "/api/users/me/profile-image/rotate", json={"degrees": 180}, headers=h
    )
    assert r.status_code == 200, r.text
    new = r.json()["profile_image_path"]
    assert new != old and _size(new) == (200, 100)
    me = await unauthenticated_client.get("/api/users/me", headers=h)
    assert me.json()["profile_image_path"] == new


@pytest.mark.asyncio
async def test_rotate_profile_image_without_one_is_404(unauthenticated_client, test_breeder):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        "/api/users/me/profile-image/rotate", json={"degrees": 90}, headers=h
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_phone_photo_exif_orientation_is_applied_on_upload(
    unauthenticated_client, test_breeder, breeder_pet
):
    # Orientation 6 = "rotate 90° clockwise to display" (typical portrait phone shot).
    h = await _login(unauthenticated_client, test_breeder.email)
    img = await _upload_pet_image(
        unauthenticated_client, h, breeder_pet.id, _jpeg(200, 100, orientation=6)
    )
    assert _size(img["image_path"]) == (100, 200)
