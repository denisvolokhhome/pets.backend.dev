"""make_date_of_litter_nullable

Revision ID: 4377215edbd1
Revises: 26a96605f43d
Create Date: 2026-01-25 17:06:40.737525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4377215edbd1'
down_revision: Union[str, Sequence[str], None] = '26a96605f43d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Make date_of_litter nullable
    op.alter_column('litters', 'date_of_litter',
                    existing_type=sa.Date(),
                    nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Make date_of_litter non-nullable again
    op.alter_column('litters', 'date_of_litter',
                    existing_type=sa.Date(),
                    nullable=False)
