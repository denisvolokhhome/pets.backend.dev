"""add_pending_plan_to_subscriptions

Revision ID: cb0a3ed71e44
Revises: o2p3q4r5s6t7
Create Date: 2026-05-17 15:16:34.576031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cb0a3ed71e44'
down_revision: Union[str, Sequence[str], None] = 'o2p3q4r5s6t7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pending_plan_id and pending_plan_effective_date to subscriptions."""
    op.add_column('subscriptions', sa.Column('pending_plan_id', sa.UUID(), nullable=True))
    op.add_column('subscriptions', sa.Column('pending_plan_effective_date', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'fk_subscriptions_pending_plan_id',
        'subscriptions', 'plans',
        ['pending_plan_id'], ['id']
    )


def downgrade() -> None:
    """Remove pending_plan_id and pending_plan_effective_date from subscriptions."""
    op.drop_constraint('fk_subscriptions_pending_plan_id', 'subscriptions', type_='foreignkey')
    op.drop_column('subscriptions', 'pending_plan_effective_date')
    op.drop_column('subscriptions', 'pending_plan_id')
