"""add phone_number to users

Revision ID: 20260217222914
Revises: 9f17d8bdf049
Create Date: 2026-02-17 22:29:14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260217222914'
down_revision = '9f17d8bdf049'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add phone_number column to users table."""
    op.add_column('users', sa.Column('phone_number', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove phone_number column from users table."""
    op.drop_column('users', 'phone_number')
