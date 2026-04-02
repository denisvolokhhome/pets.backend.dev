"""add billing tables

Revision ID: 5c4429b7d69d
Revises: l9m0n1o2p3q4
Create Date: 2026-04-01 00:02:28.866561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5c4429b7d69d'
down_revision: Union[str, Sequence[str], None] = 'l9m0n1o2p3q4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Auto-generated: billing tables ---
    op.create_table('plans',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('billing_interval', sa.String(length=50), nullable=False),
        sa.Column('max_pets', sa.Integer(), nullable=False),
        sa.Column('max_published_locations', sa.Integer(), nullable=False),
        sa.Column('max_simultaneous_offsprings', sa.Integer(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_table('subscriptions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_table('invoices',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stripe_invoice_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoices_subscription_id'), 'invoices', ['subscription_id'], unique=False)

    # Seed default FREE plan
    op.execute(
        """
        INSERT INTO plans (id, name, price, currency, billing_interval, max_pets, max_published_locations, max_simultaneous_offsprings, is_default, created_at)
        VALUES (gen_random_uuid(), 'Free', 0, 'usd', 'month', 5, 1, 20, true, now())
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove seed data before dropping tables
    op.execute("DELETE FROM plans WHERE name = 'Free' AND is_default = true")

    op.drop_index(op.f('ix_invoices_subscription_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_table('plans')
