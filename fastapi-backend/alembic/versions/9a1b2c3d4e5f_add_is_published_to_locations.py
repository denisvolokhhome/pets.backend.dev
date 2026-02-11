"""add_is_published_to_locations

Revision ID: 9a1b2c3d4e5f
Revises: 8f602ce5a841
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, None] = '8f602ce5a841'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_published column to locations table."""
    op.add_column('locations', sa.Column('is_published', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Remove is_published column from locations table."""
    op.drop_column('locations', 'is_published')
