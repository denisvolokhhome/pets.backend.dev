"""merge_heads

Revision ID: j7k8l9m0n1o2
Revises: 219c6d656507, i6j7k8l9m0n1
Create Date: 2026-03-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j7k8l9m0n1o2'
down_revision: Union[str, Sequence[str], None] = ('219c6d656507', 'i6j7k8l9m0n1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration - no changes needed."""
    pass


def downgrade() -> None:
    """Merge migration - no changes needed."""
    pass
