"""merge offspring and pet_images migrations

Revision ID: bec93c200a00
Revises: 03ff9cd396e5, h5i6j7k8l9m0
Create Date: 2026-03-03 22:35:06.908704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bec93c200a00'
down_revision: Union[str, Sequence[str], None] = ('03ff9cd396e5', 'h5i6j7k8l9m0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
