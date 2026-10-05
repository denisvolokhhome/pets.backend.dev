"""
Breedly API load test (Locust).

Models realistic traffic:
  * AnonymousVisitor (weight 7) — browses pricing, searches the map, opens breeder
    profiles and offspring listings. No account.
  * PetSeeker (weight 2) — signed in; dashboard, notifications polling, favorites,
    messages, occasionally sends a message.
  * Breeder (weight 1) — signed in; dashboard, pets/breedings/offspring management views.

Each simulated user sends its own X-Forwarded-For address so per-IP rate limits behave
like real, distinct clients behind the reverse proxy.

Setup (accounts + data) — see loadtest/README.md:
    LOADTEST_PASSWORD=...  python loadtest/seed_users.py --host http://localhost:8001

Run:
    locust -f loadtest/locustfile.py --host http://localhost:8001 \
           --headless -u 100 -r 10 -t 3m --csv loadtest/results/run
"""
import itertools
import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

ZIP_CODES = ["21701", "21702", "21703", "21704", "21740", "20850", "20874", "21228"]
RADII = [10, 20, 40, 60]

_ip_counter = itertools.count(1)
_accounts = json.loads(Path(__file__).with_name("accounts.json").read_text()) if Path(__file__).with_name("accounts.json").exists() else {"seekers": [], "breeders": []}
_seekers = itertools.cycle(_accounts["seekers"] or [None])
_breeders = itertools.cycle(_accounts["breeders"] or [None])
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "LoadTest2026!")


def _fake_ip() -> str:
    n = next(_ip_counter)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


class _Base(HttpUser):
    abstract = True

    def on_start(self):
        self.client.headers["X-Forwarded-For"] = _fake_ip()
        self.breeder_ids = []
        self.offspring_ids = []

    # ── shared browsing ──────────────────────────────────────────────
    def _search(self):
        # Same as the app: geocode the ZIP, then radius-search by coordinates
        g = self.client.get("/api/geocode/zip", params={"zip": random.choice(ZIP_CODES)}, name="GET /api/geocode/zip")
        if g.status_code != 200:
            return
        coords = g.json()
        params = {"latitude": coords["latitude"], "longitude": coords["longitude"], "radius": random.choice(RADII)}
        with self.client.get("/api/search/breeders", params=params, name="GET /api/search/breeders", catch_response=True) as r:
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("results") or data.get("breeders") or []
                self.breeder_ids = [b.get("user_id") or b.get("id") for b in items if b.get("user_id") or b.get("id")]
                r.success()
            elif r.status_code == 404:
                r.success()  # no breeders in that area is a valid answer
            else:
                r.failure(f"{r.status_code}")

    def _breeder_profile_and_listings(self):
        if not self.breeder_ids:
            return
        breeder = random.choice(self.breeder_ids)
        self.client.get(f"/api/users/breeder/{breeder}/public", name="GET /api/users/breeder/{id}/public")
        self.client.get(f"/api/reviews/breeder/{breeder}/summary", name="GET /api/reviews/breeder/{id}/summary")
        r = self.client.get(f"/api/offsprings/public/breeder/{breeder}", name="GET /api/offsprings/public/breeder/{id}")
        if r.status_code == 200:
            self.offspring_ids = [o["id"] for o in r.json().get("offsprings", [])]

    def _offspring_detail(self):
        if self.offspring_ids:
            oid = random.choice(self.offspring_ids)
            self.client.get(f"/api/offsprings/public/{oid}", name="GET /api/offsprings/public/{id}")


class AnonymousVisitor(_Base):
    weight = 7
    wait_time = between(2, 6)

    @task(2)
    def pricing(self):
        self.client.get("/api/billing/plans", name="GET /api/billing/plans")

    @task(4)
    def search(self):
        self._search()

    @task(3)
    def breeder(self):
        self._breeder_profile_and_listings()

    @task(3)
    def offspring(self):
        self._offspring_detail()

    @task(1)
    def breeds(self):
        self.client.get("/api/breeds", params={"limit": 1000}, name="GET /api/breeds")


class _SignedIn(_Base):
    abstract = True
    accounts = None

    def on_start(self):
        super().on_start()
        email = next(self.accounts)
        if not email:
            self.environment.runner.quit()
            return
        r = self.client.post("/api/auth/jwt/login", data={"username": email, "password": PASSWORD},
                             name="POST /api/auth/jwt/login")
        if r.status_code == 200:
            self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
            self.user_id = self.client.get("/api/auth/users/me", name="GET /api/auth/users/me").json()["id"]

    @task(3)
    def poll_notifications(self):
        # The app polls these every 30s while signed in
        self.client.get("/api/notifications/unread/count", name="GET /api/notifications/unread/count")
        self.client.get("/api/messages/unread-count", name="GET /api/messages/unread-count")


class PetSeeker(_SignedIn):
    weight = 2
    wait_time = between(3, 8)
    accounts = _seekers

    @task(2)
    def dashboard(self):
        self.client.get("/api/favorites/offsprings", params={"limit": 50}, name="GET /api/favorites/offsprings")
        self.client.get("/api/messages/", params={"limit": 20}, name="GET /api/messages/")

    @task(3)
    def browse(self):
        self._search()
        self._breeder_profile_and_listings()
        self._offspring_detail()

    @task(1)
    def favorite_toggle(self):
        if not self.offspring_ids:
            return
        oid = random.choice(self.offspring_ids)
        r = self.client.post(f"/api/favorites/offsprings/{oid}", name="POST /api/favorites/offsprings/{id}")
        if r.status_code in (200, 201):
            self.client.delete(f"/api/favorites/offsprings/{oid}", name="DELETE /api/favorites/offsprings/{id}")

    @task(1)
    def send_message(self):
        if not (self.breeder_ids and self.offspring_ids):
            return
        self.client.post(
            f"/api/messages/offspring/{random.choice(self.offspring_ids)}",
            json={"message": "Load-test inquiry — is this offspring still available?"},
            name="POST /api/messages/offspring/{id}",
        )


class Breeder(_SignedIn):
    weight = 1
    wait_time = between(3, 8)
    accounts = _breeders

    @task(3)
    def manage(self):
        self.client.get(f"/api/pets/breeder/{self.user_id}", name="GET /api/pets/breeder/{id}")
        self.client.get("/api/breedings/", name="GET /api/breedings/")
        self.client.get("/api/offsprings/", name="GET /api/offsprings/")

    @task(2)
    def inbox(self):
        self.client.get("/api/messages/", params={"limit": 20}, name="GET /api/messages/")
        self.client.get("/api/notifications/", params={"limit": 10}, name="GET /api/notifications/")

    @task(1)
    def settings_pages(self):
        self.client.get("/api/locations/", name="GET /api/locations/")
        self.client.get("/api/billing/subscription", name="GET /api/billing/subscription")
