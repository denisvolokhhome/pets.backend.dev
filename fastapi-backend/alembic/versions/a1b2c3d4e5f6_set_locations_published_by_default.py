"""set_locations_published_by_default

Revision ID: a1b2c3d4e5f6
Revises: 9a1b2c3d4e5f
Create Date: 2026-02-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change default value of is_published to true for locations table.
    
    This makes locations published by default so they appear in map searches.
    Also updates existing unpublished locations to be published.
    """
    # First, update existing locations to be published
    op.execute("UPDATE locations SET is_published = true WHERE is_published = false")
    
    # Then change the default value for new locations
    op.alter_column('locations', 'is_published',
                    server_default='true',
                    existing_type=sa.Boolean(),
                    existing_nullable=False)


def downgrade() -> None:
    """Revert default value of is_published to false."""
    op.alter_column('locations', 'is_published',
                    server_default='false',
                    existing_type=sa.Boolean(),
                    existing_nullable=False)

