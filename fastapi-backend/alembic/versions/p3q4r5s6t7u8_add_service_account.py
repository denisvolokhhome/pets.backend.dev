"""add_service_account

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'p3q4r5s6t7u8'
down_revision: Union[str, Sequence[str], None] = 'o2p3q4r5s6t7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def derive_account_type(is_breeder: bool) -> str:
    """Derive account_type string from the legacy is_breeder boolean.

    Returns:
        "breeder" when is_breeder is True, "pet_seeker" otherwise.
    """
    return "breeder" if is_breeder else "pet_seeker"


def upgrade() -> None:
    """Add service account tables and account_type column to users."""

    # ── service_categories ────────────────────────────────────────────────────
    op.create_table(
        "service_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=100), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        op.f("ix_service_categories_slug"),
        "service_categories",
        ["slug"],
        unique=True,
    )

    # ── user_service_categories ───────────────────────────────────────────────
    op.create_table(
        "user_service_categories",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["service_categories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "category_id"),
        sa.UniqueConstraint(
            "user_id", "category_id", name="uq_user_service_category"
        ),
    )

    # ── services ──────────────────────────────────────────────────────────────
    op.create_table(
        "services",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_from", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_to", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "price_unit",
            sa.String(length=20),
            nullable=True,
            comment="per_session | per_hour | per_day | per_visit",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "price_unit IN ('per_session', 'per_hour', 'per_day', 'per_visit') OR price_unit IS NULL",
            name="ck_services_price_unit",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["service_categories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_services_is_deleted"), "services", ["is_deleted"], unique=False
    )
    op.create_index(
        op.f("ix_services_user_id"), "services", ["user_id"], unique=False
    )

    # ── service_locations ─────────────────────────────────────────────────────
    op.create_table(
        "service_locations",
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("service_id", "location_id"),
    )

    # ── service_images ────────────────────────────────────────────────────────
    op.create_table(
        "service_images",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_images_display_order"),
        "service_images",
        ["display_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_service_images_service_id"),
        "service_images",
        ["service_id"],
        unique=False,
    )

    # ── users.account_type column ─────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "account_type",
            sa.String(length=20),
            server_default="breeder",
            nullable=False,
            comment="Account type: breeder, pet_seeker, or service",
        ),
    )
    op.create_index(
        op.f("ix_users_account_type"), "users", ["account_type"], unique=False
    )
    op.create_check_constraint(
        "ck_users_account_type",
        "users",
        "account_type IN ('breeder', 'pet_seeker', 'service')",
    )

    # ── Data migration: derive account_type from is_breeder ───────────────────
    op.execute(
        "UPDATE users SET account_type = CASE WHEN is_breeder THEN 'breeder' ELSE 'pet_seeker' END "
        "WHERE account_type IS NULL OR account_type = 'breeder'"
    )


def downgrade() -> None:
    """Remove service account tables and account_type column from users."""

    # Remove users.account_type
    op.drop_constraint("ck_users_account_type", "users", type_="check")
    op.drop_index(op.f("ix_users_account_type"), table_name="users")
    op.drop_column("users", "account_type")

    # Drop service_images
    op.drop_index(op.f("ix_service_images_service_id"), table_name="service_images")
    op.drop_index(op.f("ix_service_images_display_order"), table_name="service_images")
    op.drop_table("service_images")

    # Drop service_locations
    op.drop_table("service_locations")

    # Drop services
    op.drop_index(op.f("ix_services_user_id"), table_name="services")
    op.drop_index(op.f("ix_services_is_deleted"), table_name="services")
    op.drop_table("services")

    # Drop user_service_categories
    op.drop_table("user_service_categories")

    # Drop service_categories
    op.drop_index(
        op.f("ix_service_categories_slug"), table_name="service_categories"
    )
    op.drop_table("service_categories")
