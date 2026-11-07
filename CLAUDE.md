# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

- `fastapi-backend/` — the Breedly API (FastAPI + async SQLAlchemy + PostgreSQL/PostGIS). Almost all work happens here; run commands from this directory.
- `deploy/Dockerfile` — production image, built from the repo root (`docker build -f deploy/Dockerfile .`).
- `delivery/docker-compose.yml` — dev-server stack (postgres/PostGIS, redis, one-shot `migration` = `alembic upgrade head`, one-shot `seed` = `db/seed_breeds.py` + `scripts/seed_service_categories.py`, then `backend`).
- `Jenkinsfile` — builds the image, pushes to Harbor, deploys to the dev server (api-dev.breedly.us).
- `billing-admin/` — separate Streamlit billing dashboard reading the same DB directly (`app.py`, `db.py`, own Dockerfile/Jenkinsfile).

## Commands (from `fastapi-backend/`)

`requirements.txt` is the source of truth for dependencies (it's what the Docker image installs); `pyproject.toml`'s Poetry deps are outdated and missing packages (geoalchemy2, redis, stripe, …), but it still holds the pytest/ruff/mypy config.

```bash
pip install -r requirements.txt
cp .env.example .env                       # DATABASE_URL must be postgresql+asyncpg://, SECRET_KEY >= 32 chars
alembic upgrade head
uvicorn app.main:app --reload              # docs at /api/docs

# Tests need PostGIS at localhost:5432 (test/test/test_db), connection string is hardcoded in tests/conftest.py
docker compose -f docker-compose.test.yml up -d
pytest                                     # addopts already include -v and --cov
pytest tests/unit/test_waitlist_rules.py
pytest tests/integration/test_waitlist_api.py::test_name
pytest --no-cov -x tests/unit              # faster feedback

ruff check app tests
alembic revision --autogenerate -m "msg"
```

The README mentions `tests/property/` and `POSTGIS_SETUP_SUMMARY.md`; neither exists.

## Architecture

**Layering:** `routers/` (thin HTTP layer) → `services/` (business logic, usually a module-level singleton such as `waitlist_service = WaitlistService()`) → `models/` (SQLAlchemy 2.0 declarative, `app.database.Base`). Pydantic request/response models live in `schemas/`. Newer features (`breeding_planner_*`, `waitlist_*`) split pure, DB-free logic into `*_rules.py` modules (ordering, state transitions, due dates) that are unit-tested on their own, with the `*_service.py` doing persistence.

**Sessions/transactions:** `get_async_session` (app/database.py) commits on success and rolls back on exception. Services also call `await db.commit()` explicitly. `expire_on_commit=False`. Be careful with lazy-loaded relationships in async code; use eager loading.

**Auth:** fastapi-users with JWT bearer (`app/dependencies.py`). Use `current_active_user`, `optional_current_user`, `current_superuser`, and role guards `require_breeder`, `require_pet_seeker`, `require_service_provider`. `User.account_type` is `breeder` | `pet_seeker` | `service_provider`. Plan-limit dependencies (`check_pet_limit`, `check_location_limit`, `check_offspring_limit`) enforce billing tiers. Google OAuth lives in `routers/auth.py`.

**Feature flags** (`app/config.py` Settings, env vars): `ENABLE_SERVICE_PROVIDERS` and `ENABLE_WAITLIST` both default off. They're enforced by `require_service_providers_enabled` / `require_waitlist_enabled`; the waitlist router attaches its flag check as a router-level dependency, so the whole router returns 404 when it's off. `ENABLE_WAITLIST` must match the frontend's `environment.enableWaitlist`. `tests/conftest.py` turns service providers on so the general suite exercises them.

**app/main.py wiring things to know:**
- Router order matters: `breeding_planner` and `waitlist` are included **before** `breedings`, so `/api/breedings/milestones/...` doesn't match `/api/breedings/{breeding_id}`.
- CORS middleware is added **last** on purpose, which makes it the outermost layer and keeps CORS headers on responses produced by inner middleware (e.g. the billing rate limiter's 429). `tests/unit/test_middleware_order.py` checks this.
- All errors are returned as `{"detail": ..., "error_code": ...}` by the global handlers. Validation failures on `/api/billing/*` are also written to the billing audit log.
- Lifespan starts the breeding-milestone reminder loop (`services/breeding_reminder_service.py`) unless `TESTING=1`.
- Uploaded files are served via `StaticFiles` mounted at `STORAGE_URL` from the parent of `STORAGE_PATH`.

**Database:** PostGIS is required (`Location` has a geometry column via geoalchemy2; breeder search uses `ST_DWithin`). Redis caches Nominatim geocoding results. Most main entities have UUID primary keys, but some (e.g. breedings) use integer IDs. The API originally mirrored a Laravel implementation, so keep the `/api/` URL shapes and response formats compatible.

**Migrations:** Alembic, async (`alembic/env.py` reads `DATABASE_URL` from Settings). Revision IDs are a mix of real hashes and hand-written ones, and there have been several merge-head migrations. Run `alembic heads` before adding a revision. Register new models in `app/models/__init__.py` so both Alembic and test `create_all` pick them up.

**Tests:** `tests/conftest.py` sets env vars before importing the app (`TESTING=1` skips `.env`). The `async_session` fixture builds the schema with `Base.metadata.create_all` rather than migrations, and patches string `server_default`s into `text()` along the way. `async_client` overrides `get_async_session` and `current_active_user` with `test_user`. `unauthenticated_client` overrides only the session. The in-memory rate limiter is reset before each test.

**Billing:** Stripe via `services/stripe_gateway.py` and `billing_service.py`. Sensitive columns use `models/encrypted_type.py` (`BILLING_ENCRYPTION_KEY`). Billing endpoints have their own rate limiter and security-header middleware. Invoices are generated by `scripts/run_invoice_job.py`.

Feature-level docs live in `fastapi-backend/docs/` (messages architecture, geocoding, map search API, environment variables, deployment checklist).
