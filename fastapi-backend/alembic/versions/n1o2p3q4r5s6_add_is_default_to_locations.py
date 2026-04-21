"""add_is_default_to_locations

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, None] = '52b58e465c49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'locations',
        sa.Column(
            'is_default',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Whether this is the default location for new pets'
        )
    )


def downgrade() -> None:
    op.drop_column('locations', 'is_default')
