"""merge_heads

Revision ID: 52b58e465c49
Revises: 383e3fcc6d06, m0n1o2p3q4r5
Create Date: 2026-04-19 09:45:43.940730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52b58e465c49'
down_revision: Union[str, Sequence[str], None] = ('383e3fcc6d06', 'm0n1o2p3q4r5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
