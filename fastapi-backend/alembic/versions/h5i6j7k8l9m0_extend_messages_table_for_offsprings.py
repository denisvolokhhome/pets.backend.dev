"""extend_messages_table_for_offsprings

Revision ID: h5i6j7k8l9m0
Revises: g4h5i6j7k8l9
Create Date: 2026-03-03 10:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'h5i6j7k8l9m0'
down_revision: Union[str, Sequence[str], None] = 'g4h5i6j7k8l9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add offspring_id and thread_id columns to messages table."""
    # Add offspring_id column
    op.add_column(
        'messages',
        sa.Column('offspring_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Add thread_id column
    op.add_column(
        'messages',
        sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Create foreign key constraint with SET NULL delete
    op.create_foreign_key(
        'fk_messages_offspring_id',
        'messages', 'offsprings',
        ['offspring_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Create indexes
    op.create_index('ix_messages_offspring_id', 'messages', ['offspring_id'])
    op.create_index('ix_messages_thread_id', 'messages', ['thread_id'])


def downgrade() -> None:
    """Remove offspring_id and thread_id columns from messages table."""
    # Drop indexes
    op.drop_index('ix_messages_thread_id', 'messages')
    op.drop_index('ix_messages_offspring_id', 'messages')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_messages_offspring_id', 'messages', type_='foreignkey')
    
    # Drop columns
    op.drop_column('messages', 'thread_id')
    op.drop_column('messages', 'offspring_id')
