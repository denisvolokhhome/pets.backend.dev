"""Unit tests for database migrations."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_all_required_tables_exist(async_session: AsyncSession):
    """
    Test that all required tables exist after migration.
    
    Validates: Requirements 2.2, 11.4
    """
    # Get table names from database
    result = await async_session.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename != 'alembic_version'"
        )
    )
    tables = {row[0] for row in result.fetchall()}
    
    # Required tables based on models
    required_tables = {
        "users",
        "pets",
        "breeds",
        "breed_colours",
        "litters",
        "locations",
        "user_contacts"
    }
    
    # Verify all required tables exist
    assert required_tables.issubset(tables), (
        f"Missing tables: {required_tables - tables}"
    )


@pytest.mark.asyncio
async def test_users_table_schema(async_session: AsyncSession):
    """
    Test that users table has correct schema.
    
    Validates: Requirements 2.2, 11.3
    """
    result = await async_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'users' "
            "ORDER BY ordinal_position"
        )
    )
    columns = {row[0]: (row[1], row[2]) for row in result.fetchall()}
    
    # Verify key columns exist with correct types
    assert "id" in columns
    assert columns["id"][0] == "uuid"
    assert columns["id"][1] == "NO"  # NOT NULL
    
    assert "email" in columns
    assert columns["email"][0] == "character varying"
    assert columns["email"][1] == "NO"  # NOT NULL
    
    assert "hashed_password" in columns
    assert columns["hashed_password"][1] == "NO"  # NOT NULL
    
    assert "is_active" in columns
    assert columns["is_active"][0] == "boolean"
    
    assert "created_at" in columns
    assert columns["created_at"][0] == "timestamp with time zone"


@pytest.mark.asyncio
async def test_pets_table_schema(async_session: AsyncSession):
    """
    Test that pets table has correct schema.
    
    Validates: Requirements 2.2, 11.3
    """
    result = await async_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'pets' "
            "ORDER BY ordinal_position"
        )
    )
    columns = {row[0]: (row[1], row[2]) for row in result.fetchall()}
    
    # Verify key columns exist with correct types
    assert "id" in columns
    assert columns["id"][0] == "uuid"
    assert columns["id"][1] == "NO"  # NOT NULL
    
    assert "user_id" in columns
    assert columns["user_id"][0] == "uuid"
    assert columns["user_id"][1] == "NO"  # NOT NULL
    
    assert "breed_id" in columns
    assert columns["breed_id"][0] == "integer"
    assert columns["breed_id"][1] == "YES"  # NULLABLE
    
    assert "name" in columns
    assert columns["name"][1] == "NO"  # NOT NULL
    
    assert "microchip" in columns
    assert "vaccination" in columns
    assert "health_certificate" in columns
    assert "deworming" in columns
    assert "birth_certificate" in columns
    
    assert "image_path" in columns
    assert "image_file_name" in columns
    
    assert "is_deleted" in columns
    assert columns["is_deleted"][0] == "boolean"
    assert columns["is_deleted"][1] == "NO"  # NOT NULL


@pytest.mark.asyncio
async def test_foreign_key_constraints_exist(async_session: AsyncSession):
    """
    Test that all foreign key constraints are properly defined.
    
    Validates: Requirements 2.2, 11.4
    """
    # Query for foreign key constraints
    result = await async_session.execute(
        text(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name, kcu.column_name
            """
        )
    )
    foreign_keys = list(result.fetchall())
    
    # Convert to set of tuples for easier checking
    fk_set = {
        (row[0], row[1], row[2], row[3], row[4])
        for row in foreign_keys
    }
    
    # Verify key foreign key relationships exist
    # pets -> users
    assert any(
        fk[0] == "pets" and fk[1] == "user_id" and fk[2] == "users"
        for fk in fk_set
    ), "pets.user_id -> users.id foreign key missing"
    
    # pets -> breeds
    assert any(
        fk[0] == "pets" and fk[1] == "breed_id" and fk[2] == "breeds"
        for fk in fk_set
    ), "pets.breed_id -> breeds.id foreign key missing"
    
    # pets -> litters
    assert any(
        fk[0] == "pets" and fk[1] == "litter_id" and fk[2] == "litters"
        for fk in fk_set
    ), "pets.litter_id -> litters.id foreign key missing"
    
    # pets -> locations
    assert any(
        fk[0] == "pets" and fk[1] == "location_id" and fk[2] == "locations"
        for fk in fk_set
    ), "pets.location_id -> locations.id foreign key missing"
    
    # locations -> users
    assert any(
        fk[0] == "locations" and fk[1] == "user_id" and fk[2] == "users"
        for fk in fk_set
    ), "locations.user_id -> users.id foreign key missing"
    
    # breed_colours -> breeds
    assert any(
        fk[0] == "breed_colours" and fk[1] == "breed_id" and fk[2] == "breeds"
        for fk in fk_set
    ), "breed_colours.breed_id -> breeds.id foreign key missing"
    
    # user_contacts -> users
    assert any(
        fk[0] == "user_contacts" and fk[1] == "user_id" and fk[2] == "users"
        for fk in fk_set
    ), "user_contacts.user_id -> users.id foreign key missing"


@pytest.mark.asyncio
async def test_cascade_delete_rules(async_session: AsyncSession):
    """
    Test that cascade delete rules are properly configured.
    
    Validates: Requirements 2.2, 11.4
    """
    # Query for foreign key constraints with delete rules
    result = await async_session.execute(
        text(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            """
        )
    )
    foreign_keys = list(result.fetchall())
    
    # Convert to dict for easier lookup
    fk_dict = {
        (row[0], row[1], row[2]): row[3]
        for row in foreign_keys
    }
    
    # Verify cascade delete rules
    # pets.user_id -> users.id should CASCADE
    assert fk_dict.get(("pets", "user_id", "users")) == "CASCADE", (
        "pets.user_id should CASCADE on delete"
    )
    
    # pets.breed_id -> breeds.id should SET NULL
    assert fk_dict.get(("pets", "breed_id", "breeds")) == "SET NULL", (
        "pets.breed_id should SET NULL on delete"
    )
    
    # pets.litter_id -> litters.id should SET NULL
    assert fk_dict.get(("pets", "litter_id", "litters")) == "SET NULL", (
        "pets.litter_id should SET NULL on delete"
    )
    
    # locations.user_id -> users.id should CASCADE
    assert fk_dict.get(("locations", "user_id", "users")) == "CASCADE", (
        "locations.user_id should CASCADE on delete"
    )
    
    # breed_colours.breed_id -> breeds.id should CASCADE
    assert fk_dict.get(("breed_colours", "breed_id", "breeds")) == "CASCADE", (
        "breed_colours.breed_id should CASCADE on delete"
    )


@pytest.mark.asyncio
async def test_indexes_exist(async_session: AsyncSession):
    """
    Test that required indexes exist for performance.
    
    Validates: Requirements 2.2
    """
    # Query for indexes
    result = await async_session.execute(
        text(
            """
            SELECT
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND tablename IN ('users', 'pets', 'breeds', 'locations')
            ORDER BY tablename, indexname
            """
        )
    )
    indexes = list(result.fetchall())
    
    # Convert to set of (table, index_name) tuples
    index_set = {(row[0], row[1]) for row in indexes}
    
    # Verify key indexes exist
    assert ("users", "ix_users_email") in index_set, (
        "Index on users.email missing"
    )
    assert ("pets", "ix_pets_user_id") in index_set, (
        "Index on pets.user_id missing"
    )
    assert ("pets", "ix_pets_breed_id") in index_set, (
        "Index on pets.breed_id missing"
    )
    assert ("pets", "ix_pets_is_deleted") in index_set, (
        "Index on pets.is_deleted missing"
    )
    assert ("breeds", "ix_breeds_name") in index_set, (
        "Index on breeds.name missing"
    )
    assert ("locations", "ix_locations_user_id") in index_set, (
        "Index on locations.user_id missing"
    )
