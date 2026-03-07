"""restructure_messages_table

Revision ID: 9f681d1f4843
Revises: j7k8l9m0n1o2
Create Date: 2026-03-07 18:25:12.039636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f681d1f4843'
down_revision: Union[str, Sequence[str], None] = 'j7k8l9m0n1o2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
