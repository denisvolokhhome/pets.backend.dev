"""add pro and premium plans

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'o2p3q4r5s6t7'
down_revision: Union[str, Sequence[str], None] = 'n1o2p3q4r5s6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert Pro and Premium subscription plans."""
    op.execute(
        """
        INSERT INTO plans (id, name, price, currency, billing_interval,
                           max_pets, max_published_locations, max_simultaneous_offsprings,
                           is_default, created_at)
        VALUES
            (gen_random_uuid(), 'Pro',     19.00, 'usd', 'month',  25,  3,  100, false, now()),
            (gen_random_uuid(), 'Premium', 49.00, 'usd', 'month', 999, 10,  500, false, now())
        """
    )


def downgrade() -> None:
    """Remove Pro and Premium plans (only if no subscriptions reference them)."""
    op.execute("DELETE FROM plans WHERE name IN ('Pro', 'Premium')")
