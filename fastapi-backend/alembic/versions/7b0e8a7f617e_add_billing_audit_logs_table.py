"""add billing audit logs table

Revision ID: 7b0e8a7f617e
Revises: 5c4429b7d69d
Create Date: 2026-04-01 09:15:37.090245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b0e8a7f617e'
down_revision: Union[str, Sequence[str], None] = '5c4429b7d69d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('billing_audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('operation', sa.String(length=50), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_billing_audit_logs_user_id'), 'billing_audit_logs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_billing_audit_logs_user_id'), table_name='billing_audit_logs')
    op.drop_table('billing_audit_logs')
