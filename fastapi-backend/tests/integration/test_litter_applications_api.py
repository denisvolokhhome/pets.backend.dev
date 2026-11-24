"""Litter applications: public page, submit rules, breeder review, puppy assignment."""
import asyncio
import os
from datetime import date

import bcrypt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.breeding_application_form import BreedingApplicationForm
from app.models.litter_application import LitterApplication
from app.models.offspring import Offspring
from app.models.user import User

FIELDS = [
    {"id": "f1", "type": "text", "label": "Your name", "required": True},
    {"id": "f2", "type": "textarea", "label": "Home & yard", "required": False},
]


async def _auth(client, user):
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user(session, email, *, breeder=False):
    u = User(email=email, name=email.split("@")[0].title(), is_active=True, is_verified=True,
             is_breeder=breeder, account_type="breeder" if breeder else "pet_seeker",
             hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode())
    session.add(u)
    await session.commit()
    return u


async def _puppy(session, breeding, breeder, breed, name, status="Available", published=True):
    o = Offspring(breeding_id=breeding.id, user_id=breeder.id, breed_id=breed.id, name=name,
                  gender="Female", date_of_birth=date(2024, 3, 1), status=status, is_published=published)
    session.add(o)
    await session.commit()
    return o


@pytest.fixture
async def form(async_session, test_breeding, test_breeder):
    f = BreedingApplicationForm(breeding_id=test_breeding.id, user_id=test_breeder.id,
                                form_fields=FIELDS, accepting_litter_applications=True)
    async_session.add(f)
    await async_session.commit()
    return f


@pytest.fixture
async def seeker(async_session, test_pet_seeker):
    test_pet_seeker.account_type = "pet_seeker"
    await async_session.commit()
    return test_pet_seeker


async def _apply(client, breeding_id, headers, **extra):
    body = {"answers": {"f1": "Ann Family", "f2": "Big yard\nfenced"}, **extra}
    return await client.post(f"/api/breedings/public/{breeding_id}/applications", json=body, headers=headers)


# ── submitting ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_family_applies_before_puppies_exist(unauthenticated_client, test_breeding, form, seeker,
                                                   test_breeder):
    pub = await unauthenticated_client.get(f"/api/breedings/public/{test_breeding.id}")
    assert pub.status_code == 200
    assert pub.json()["accepting_applications"] is True and pub.json()["puppies"] == []

    hs = await _auth(unauthenticated_client, seeker)
    r = await _apply(unauthenticated_client, test_breeding.id, hs)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "new"

    hb = await _auth(unauthenticated_client, test_breeder)
    apps = (await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/applications", headers=hb)).json()
    assert len(apps) == 1
    app = apps[0]
    assert app["source"] == "litter" and app["assigned_offspring"] is None
    assert app["answers"] == [
        {"field_id": "f1", "label": "Your name", "value": "Ann Family"},
        {"field_id": "f2", "label": "Home & yard", "value": "Big yard\nfenced"},
    ]


@pytest.mark.asyncio
async def test_closed_form_rejects_but_keeps_past_submissions(unauthenticated_client, test_breeding, form,
                                                             seeker, test_breeder):
    hs = await _auth(unauthenticated_client, seeker)
    hb = await _auth(unauthenticated_client, test_breeder)
    assert (await _apply(unauthenticated_client, test_breeding.id, hs)).status_code == 201

    r = await unauthenticated_client.put(
        f"/api/breedings/{test_breeding.id}/application-form/litter-applications",
        json={"accepting_litter_applications": False}, headers=hb)
    assert r.status_code == 200 and r.json()["accepting_litter_applications"] is False

    r = await _apply(unauthenticated_client, test_breeding.id, hs)
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    pub = (await unauthenticated_client.get(f"/api/breedings/public/{test_breeding.id}")).json()
    assert pub["accepting_applications"] is False
    apps = (await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/applications", headers=hb)).json()
    assert len(apps) == 1


@pytest.mark.asyncio
async def test_voided_litter_is_not_public(unauthenticated_client, async_session, test_breeding, form, seeker):
    test_breeding.status = "Voided"
    await async_session.commit()
    assert (await unauthenticated_client.get(f"/api/breedings/public/{test_breeding.id}")).status_code == 404
    hs = await _auth(unauthenticated_client, seeker)
    assert (await _apply(unauthenticated_client, test_breeding.id, hs)).status_code == 404


@pytest.mark.asyncio
async def test_required_answers_and_auth(unauthenticated_client, test_breeding, form, seeker, test_breeder):
    r = await _apply(unauthenticated_client, test_breeding.id, {})
    assert r.status_code == 401
    hs = await _auth(unauthenticated_client, seeker)
    r = await unauthenticated_client.post(f"/api/breedings/public/{test_breeding.id}/applications",
                                          json={"answers": {"f1": "   "}}, headers=hs)
    assert r.status_code == 422 and "Your name" in r.json()["detail"]
    hb = await _auth(unauthenticated_client, test_breeder)
    assert (await _apply(unauthenticated_client, test_breeding.id, hb)).status_code == 403


@pytest.mark.asyncio
async def test_puppy_page_flow_still_works_when_litter_applications_closed(
        unauthenticated_client, async_session, test_breeding, form, seeker, test_breeder, test_breed):
    form.accepting_litter_applications = False
    await async_session.commit()
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    # The existing form endpoint the puppy page uses is unchanged
    r = await unauthenticated_client.get(f"/api/breedings/public/{test_breeding.id}/application-form")
    assert r.status_code == 200 and len(r.json()["form_fields"]) == 2

    hs = await _auth(unauthenticated_client, seeker)
    r = await _apply(unauthenticated_client, test_breeding.id, hs, offspring_id=str(pup.id))
    assert r.status_code == 201, r.text
    hb = await _auth(unauthenticated_client, test_breeder)
    app = (await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/applications", headers=hb)).json()[0]
    assert app["source"] == "offspring" and app["requested_offspring"]["name"] == "Rosie"
    assert app["assigned_offspring"] is None


@pytest.mark.asyncio
async def test_unpublished_puppy_cannot_be_applied_for(unauthenticated_client, async_session, test_breeding,
                                                       form, seeker, test_breeder, test_breed):
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Hidden", published=False)
    hs = await _auth(unauthenticated_client, seeker)
    r = await _apply(unauthenticated_client, test_breeding.id, hs, offspring_id=str(pup.id))
    assert r.status_code == 404


# ── breeder review & assignment ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_waitlist_then_assign_then_undo(unauthenticated_client, async_session, test_breeding, form,
                                             seeker, test_breeder, test_breed):
    hs = await _auth(unauthenticated_client, seeker)
    hb = await _auth(unauthenticated_client, test_breeder)
    app_id = (await _apply(unauthenticated_client, test_breeding.id, hs)).json()["id"]

    r = await unauthenticated_client.patch(f"/api/applications/{app_id}/status",
                                           json={"status": "waitlisted"}, headers=hb)
    assert r.json()["status"] == "waitlisted"
    r = await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/applications?status=waitlisted",
                                         headers=hb)
    assert [a["id"] for a in r.json()] == [app_id]

    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    r = await unauthenticated_client.post(f"/api/applications/{app_id}/assign",
                                          json={"offspring_id": str(pup.id)}, headers=hb)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "assigned" and body["assigned_offspring"]["status"] == "Reserved"
    assert body["answers"][0]["value"] == "Ann Family" and body["breeding_id"] == test_breeding.id

    # Status can't be changed by hand while assigned
    r = await unauthenticated_client.patch(f"/api/applications/{app_id}/status",
                                           json={"status": "new"}, headers=hb)
    assert r.status_code == 409

    r = await unauthenticated_client.post(f"/api/applications/{app_id}/unassign", headers=hb)
    assert r.status_code == 200
    assert r.json()["status"] == "waitlisted" and r.json()["assigned_offspring"] is None
    await async_session.refresh(pup)
    assert pup.status == "Available"
    assert r.json()["answers"][0]["value"] == "Ann Family"


@pytest.mark.asyncio
async def test_two_families_cannot_get_the_same_puppy(unauthenticated_client, async_session, test_breeding,
                                                      form, seeker, test_breeder, test_breed):
    other = await _user(async_session, "second.family@example.com")
    hb = await _auth(unauthenticated_client, test_breeder)
    a1 = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    a2 = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, other))).json()["id"]
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")

    r1 = await unauthenticated_client.post(f"/api/applications/{a1}/assign", json={"offspring_id": str(pup.id)}, headers=hb)
    r2 = await unauthenticated_client.post(f"/api/applications/{a2}/assign", json={"offspring_id": str(pup.id)}, headers=hb)
    assert r1.status_code == 200 and r2.status_code == 409


@pytest.mark.asyncio
async def test_puppy_reserved_by_waitlist_is_not_assignable(unauthenticated_client, async_session, test_breeding,
                                                            form, seeker, test_breeder, test_breed):
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Taken", status="Reserved")
    hb = await _auth(unauthenticated_client, test_breeder)
    app_id = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    r = await unauthenticated_client.post(f"/api/applications/{app_id}/assign",
                                          json={"offspring_id": str(pup.id)}, headers=hb)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_puppy_from_another_litter_is_rejected(unauthenticated_client, async_session, test_breeding, form,
                                                     seeker, test_breeder, test_breed):
    from app.models.breeding import Breeding
    other_litter = Breeding(user_id=test_breeder.id, description="Other", is_active=True, status="Started")
    async_session.add(other_litter)
    await async_session.commit()
    pup = await _puppy(async_session, other_litter, test_breeder, test_breed, "Elsewhere")
    hb = await _auth(unauthenticated_client, test_breeder)
    app_id = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    r = await unauthenticated_client.post(f"/api/applications/{app_id}/assign",
                                          json={"offspring_id": str(pup.id)}, headers=hb)
    assert r.status_code == 409
    await async_session.refresh(pup)
    assert pup.status == "Available"


@pytest.mark.asyncio
async def test_only_litter_owner_can_see_or_assign(unauthenticated_client, async_session, test_breeding, form,
                                                   seeker, test_breed, test_breeder):
    intruder = await _user(async_session, "other.breeder@example.com", breeder=True)
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    app_id = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    hi = await _auth(unauthenticated_client, intruder)
    assert (await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/applications", headers=hi)).status_code == 404
    assert (await unauthenticated_client.get(f"/api/applications/{app_id}", headers=hi)).status_code == 404
    r = await unauthenticated_client.post(f"/api/applications/{app_id}/assign",
                                          json={"offspring_id": str(pup.id)}, headers=hi)
    assert r.status_code == 404
    r = await unauthenticated_client.put(
        f"/api/breedings/{test_breeding.id}/application-form/litter-applications",
        json={"accepting_litter_applications": False}, headers=hi)
    assert r.status_code == 404
    # The family can't use breeder routes either
    hs = await _auth(unauthenticated_client, seeker)
    assert (await unauthenticated_client.get(f"/api/applications/{app_id}", headers=hs)).status_code == 403


@pytest.mark.asyncio
async def test_simultaneous_assignments_only_one_wins(async_session, test_breeding, form, seeker, test_breeder,
                                                      test_breed):
    """Two real connections race to give the same puppy to two families."""
    from app.services.litter_application_service import litter_application_service as svc
    other = await _user(async_session, "racer@example.com")
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    apps = []
    for applicant in (seeker, other):
        a = LitterApplication(breeding_id=test_breeding.id, breeder_id=test_breeder.id, applicant_id=applicant.id,
                              source="litter", answers=[], status="waitlisted")
        async_session.add(a)
        apps.append(a)
    await async_session.commit()

    engine = create_async_engine(os.environ.get("TEST_DATABASE_URL",
                                                "postgresql+asyncpg://test:test@localhost:5432/test_db"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def attempt(app_id):
        async with maker() as s:
            breeder = await s.get(User, test_breeder.id)
            try:
                await svc.assign(s, breeder, app_id, pup.id)
                return "ok"
            except Exception as e:  # HTTPException 409
                return getattr(e, "status_code", repr(e))

    try:
        results = await asyncio.gather(*(attempt(a.id) for a in apps))
    finally:
        await engine.dispose()
    assert sorted(map(str, results)) == ["409", "ok"]
    rows = (await async_session.execute(
        select(LitterApplication).where(LitterApplication.status == "assigned")
        .execution_options(populate_existing=True))).scalars().all()
    assert len(rows) == 1 and rows[0].assigned_offspring_id == pup.id


@pytest.mark.asyncio
async def test_duplicate_application_rejected_until_declined(unauthenticated_client, test_breeding, form,
                                                             seeker, test_breeder):
    hs = await _auth(unauthenticated_client, seeker)
    hb = await _auth(unauthenticated_client, test_breeder)
    first = await _apply(unauthenticated_client, test_breeding.id, hs)
    assert first.status_code == 201
    again = await _apply(unauthenticated_client, test_breeding.id, hs)
    assert again.status_code == 409 and "already applied" in again.json()["detail"]
    await unauthenticated_client.patch(f"/api/applications/{first.json()['id']}/status",
                                       json={"status": "declined"}, headers=hb)
    assert (await _apply(unauthenticated_client, test_breeding.id, hs)).status_code == 201


@pytest.mark.asyncio
async def test_manual_status_edit_cannot_free_a_held_puppy(unauthenticated_client, async_session, test_breeding,
                                                           form, seeker, test_breeder, test_breed):
    """A breeder flipping Reserved -> Available by hand must not let a second family take the puppy."""
    other = await _user(async_session, "late.family@example.com")
    hb = await _auth(unauthenticated_client, test_breeder)
    a1 = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    a2 = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, other))).json()["id"]
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    assert (await unauthenticated_client.post(f"/api/applications/{a1}/assign", json={"offspring_id": str(pup.id)},
                                              headers=hb)).status_code == 200
    await async_session.refresh(pup)
    pup.status = "Available"  # edited by hand while still assigned
    await async_session.commit()
    r = await unauthenticated_client.post(f"/api/applications/{a2}/assign", json={"offspring_id": str(pup.id)},
                                          headers=hb)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_undo_keeps_puppy_reserved_for_another_holder(unauthenticated_client, async_session, test_breeding,
                                                            form, seeker, test_breeder, test_breed):
    """Undoing one assignment never frees a puppy a waitlist match now holds."""
    from app.models.waitlist_entry import WaitlistEntry
    hb = await _auth(unauthenticated_client, test_breeder)
    app_id = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    assert (await unauthenticated_client.post(f"/api/applications/{app_id}/assign",
                                              json={"offspring_id": str(pup.id)}, headers=hb)).status_code == 200
    # Simulate an inconsistent second holder (e.g. created before this release)
    async_session.add(WaitlistEntry(breeder_id=test_breeder.id, source="manual", contact_name="W", status="matched",
                                    sex_preference="Any", deposit_status="none", breeding_id=test_breeding.id,
                                    offspring_id=pup.id))
    await async_session.commit()
    r = await unauthenticated_client.post(f"/api/applications/{app_id}/unassign", headers=hb)
    assert r.status_code == 200 and r.json()["status"] == "waitlisted"
    await async_session.refresh(pup)
    assert pup.status == "Reserved"


@pytest.mark.asyncio
async def test_database_blocks_duplicate_open_applications(async_session, test_breeding, form, seeker, test_breeder):
    from sqlalchemy.exc import IntegrityError
    for _ in range(2):
        async_session.add(LitterApplication(breeding_id=test_breeding.id, breeder_id=test_breeder.id,
                                            applicant_id=seeker.id, source="litter", answers=[], status="new"))
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ── emails ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sent_emails(monkeypatch):
    from app.services import email_service as email_module
    sent = []

    async def fake_send_email(self, to, subject, html, text=None):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    monkeypatch.setattr(email_module.EmailService, "send_email", fake_send_email)
    return sent


@pytest.mark.asyncio
async def test_breeder_is_emailed_about_a_new_application(unauthenticated_client, test_breeding, form, seeker,
                                                          test_breeder, sent_emails):
    r = await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))
    assert r.status_code == 201
    await asyncio.sleep(0.1)  # emails go out in a background task
    to_breeder = [e for e in sent_emails if e["to"] == test_breeder.email]
    assert len(to_breeder) == 1
    assert f"/breeding/{test_breeding.id}#applications" in to_breeder[0]["html"]


@pytest.mark.asyncio
async def test_family_is_emailed_when_accepted_and_when_a_puppy_is_reserved(
        unauthenticated_client, async_session, test_breeding, form, seeker, test_breeder, test_breed, sent_emails):
    from app.models.notification import Notification
    hb = await _auth(unauthenticated_client, test_breeder)
    app_id = (await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))).json()["id"]
    await unauthenticated_client.patch(f"/api/applications/{app_id}/status", json={"status": "contacted"}, headers=hb)
    await unauthenticated_client.patch(f"/api/applications/{app_id}/status", json={"status": "waitlisted"}, headers=hb)
    pup = await _puppy(async_session, test_breeding, test_breeder, test_breed, "Rosie")
    await unauthenticated_client.post(f"/api/applications/{app_id}/assign", json={"offspring_id": str(pup.id)},
                                      headers=hb)
    await asyncio.sleep(0.1)

    to_family = [e for e in sent_emails if e["to"] == seeker.email]
    assert len(to_family) == 2  # waitlisted + reserved; "contacted" sends nothing
    assert "waitlist" in to_family[0]["subject"].lower()
    assert "reserved" in to_family[1]["subject"].lower() and "Rosie" in to_family[1]["html"]
    assert f"/litter/{test_breeding.id}" in to_family[1]["html"]
    notes = (await async_session.execute(select(Notification).where(Notification.user_id == seeker.id))).scalars().all()
    assert sorted(n.type for n in notes) == ["application_update", "application_update"]


@pytest.mark.asyncio
async def test_application_emails_respect_the_preference(unauthenticated_client, test_breeding, form, seeker,
                                                         test_breeder, sent_emails):
    hb = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.put("/api/notification-preferences", json={"application_update": False},
                                         headers=hb)
    assert r.status_code == 200 and r.json()["application_update"] is False
    await _apply(unauthenticated_client, test_breeding.id, await _auth(unauthenticated_client, seeker))
    await asyncio.sleep(0.1)
    assert [e for e in sent_emails if e["to"] == test_breeder.email] == []
