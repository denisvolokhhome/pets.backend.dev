"""create_messages_table

Revision ID: b1c2d3e4f5g6
Revises: a1b2c3d4e5f6
Create Date: 2026-02-10 23:07:35.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create messages table for breeder-user communication."""
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('breeder_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sender_name', sa.String(255), nullable=False),
        sa.Column('sender_email', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_messages_breeder_id',
        'messages', 'users',
        ['breeder_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for performance
    op.create_index('ix_messages_breeder_id', 'messages', ['breeder_id'])
    op.create_index('ix_messages_is_read', 'messages', ['is_read'])
    op.create_index('ix_messages_sender_email', 'messages', ['sender_email'])
    op.create_index('ix_messages_created_at', 'messages', ['created_at'])


def downgrade() -> None:
    """Drop messages table."""
    op.drop_index('ix_messages_created_at', 'messages')
    op.drop_index('ix_messages_sender_email', 'messages')
    op.drop_index('ix_messages_is_read', 'messages')
    op.drop_index('ix_messages_breeder_id', 'messages')
    op.drop_constraint('fk_messages_breeder_id', 'messages', type_='foreignkey')
    op.drop_table('messages')
