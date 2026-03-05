"""create_notifications_table

Revision ID: g4h5i6j7k8l9
Revises: f3g4h5i6j7k8
Create Date: 2026-03-03 10:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'g4h5i6j7k8l9'
down_revision: Union[str, Sequence[str], None] = 'f3g4h5i6j7k8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notifications table for breeder notifications."""
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('related_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('related_type', sa.String(50), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        
        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_notifications_user_id', ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade() -> None:
    """Drop notifications table."""
    op.drop_index('ix_notifications_created_at', 'notifications')
    op.drop_index('ix_notifications_is_read', 'notifications')
    op.drop_index('ix_notifications_user_id', 'notifications')
    op.drop_table('notifications')
