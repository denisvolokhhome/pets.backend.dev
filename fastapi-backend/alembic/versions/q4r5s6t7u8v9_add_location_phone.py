"""add optional public phone to locations

Revision ID: q4r5s6t7u8v9
Revises: 3b05333d67ba
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'q4r5s6t7u8v9'
down_revision: Union[str, Sequence[str], None] = '3b05333d67ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('locations', sa.Column('phone', sa.String(length=32), nullable=True))
    op.add_column(
        'locations',
        sa.Column('show_phone', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('locations', 'show_phone')
    op.drop_column('locations', 'phone')
