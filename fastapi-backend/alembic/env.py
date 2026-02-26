"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

import geoalchemy2  # noqa - required so autogenerate can render geometry column types
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import the Base and settings from our application
from app.database import Base
from app.config import Settings

config = context.config

# Load settings from environment
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models here so Alembic can detect them
from app.models import User, Pet, Breed, BreedColour, Breeding, BreedingPet, Location, UserContact  # noqa
target_metadata = Base.metadata


# ── Tables to ignore completely ───────────────────────────────────────────────

POSTGIS_TABLES = {
    "spatial_ref_sys",
    "geometry_columns",
    "geography_columns",
    "raster_columns",
    "raster_overviews",
}

TIGER_TABLES = {
    "addr", "addrfeat", "bg", "county", "county_lookup", "countysub_lookup",
    "cousub", "direction_lookup", "edges", "faces", "featnames",
    "geocode_settings", "geocode_settings_default", "loader_lookuptables",
    "loader_platform", "loader_variables", "pagc_gaz", "pagc_lex",
    "pagc_rules", "place", "place_lookup", "secondary_unit_lookup",
    "state", "state_lookup", "street_type_lookup", "tabblock", "tabblock20",
    "tract", "zcta5", "zip_lookup", "zip_lookup_all", "zip_lookup_base",
    "zip_state", "zip_state_loc",
}

IGNORED_TABLES = POSTGIS_TABLES | TIGER_TABLES

# ── Stale indexes in the DB that no longer match model index names ────────────
# Alembic sees these as "drop old / create new" on every autogenerate.
# Once your DB indexes are in sync you can remove these.

IGNORED_INDEXES = {
    "ix_litter_pets_litter_id",   # renamed to ix_breeding_pets_breeding_id
    "ix_litter_pets_pet_id",      # renamed to ix_breeding_pets_pet_id
    "ix_litters_user_id",         # renamed to ix_breedings_user_id
}


def include_object(object, name, type_, reflected, compare_to):
    """Skip PostGIS/Tiger tables and stale indexes from autogenerate."""
    if type_ == "table" and name in IGNORED_TABLES:
        return False
    if type_ == "index" and name in IGNORED_INDEXES:
        return False
    return True


def include_name(name, type_, parent_names):
    """Skip columns that only exist in the DB (already removed from models)."""
    # breed_colours.code was removed from the model but may still be in the DB
    if type_ == "column" and parent_names.get("table_name") == "breed_colours" and name == "code":
        return False
    return True

# ─────────────────────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        include_name=include_name,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def do_run_migrations(connection: Connection) -> None:
        await connection.run_sync(do_run_migrations_sync)

    def do_run_migrations_sync(connection: Connection) -> None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_name=include_name,
            compare_type=True,             # Detect column type changes
            compare_server_default=False,  # Avoids noise from PostGIS/boolean defaults
        )

        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await do_run_migrations(connection)
        await connectable.dispose()

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()