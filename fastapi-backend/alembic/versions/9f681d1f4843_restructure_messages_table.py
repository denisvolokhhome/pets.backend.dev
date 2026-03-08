"""restructure_messages_table

Revision ID: 9f681d1f4843
Revises: j7k8l9m0n1o2
Create Date: 2026-03-07 18:25:12.039636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9f681d1f4843'
down_revision: Union[str, Sequence[str], None] = 'j7k8l9m0n1o2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - restructure messages table."""
    
    # Create new messages table with clean structure
    op.create_table(
        'messages_new',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('receiver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('context_type', sa.String(50), nullable=True),
        sa.Column('context_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for performance
    op.create_index('idx_messages_new_sender', 'messages_new', ['sender_id'])
    op.create_index('idx_messages_new_receiver', 'messages_new', ['receiver_id'])
    op.create_index('idx_messages_new_thread', 'messages_new', ['thread_id'])
    op.create_index('idx_messages_new_created', 'messages_new', ['created_at'], postgresql_ops={'created_at': 'DESC'})
    op.create_index('idx_messages_new_conversation', 'messages_new', ['thread_id', 'created_at'], postgresql_ops={'created_at': 'DESC'})
    op.create_index('idx_messages_new_unread', 'messages_new', ['receiver_id', 'is_read'], postgresql_where=sa.text('is_read = false'))
    op.create_index('idx_messages_new_context', 'messages_new', ['context_type', 'context_id'])
    
    # Migrate data from old messages table to new structure
    # 1. Migrate pet seeker messages (original messages)
    op.execute("""
        INSERT INTO messages_new (id, sender_id, receiver_id, thread_id, content, context_type, context_id, is_read, created_at, updated_at)
        SELECT 
            id,
            COALESCE(pet_seeker_id, breeder_id) as sender_id,
            breeder_id as receiver_id,
            COALESCE(thread_id, id) as thread_id,
            COALESCE(message, '') as content,
            CASE WHEN offspring_id IS NOT NULL THEN 'offspring' ELSE NULL END as context_type,
            offspring_id as context_id,
            is_read,
            created_at,
            updated_at
        FROM messages
        WHERE message IS NOT NULL AND message != ''
    """)
    
    # 2. Migrate breeder responses as separate messages
    op.execute("""
        INSERT INTO messages_new (sender_id, receiver_id, thread_id, content, context_type, context_id, is_read, created_at, updated_at)
        SELECT 
            breeder_id as sender_id,
            COALESCE(pet_seeker_id, breeder_id) as receiver_id,
            COALESCE(thread_id, id) as thread_id,
            response_text as content,
            CASE WHEN offspring_id IS NOT NULL THEN 'offspring' ELSE NULL END as context_type,
            offspring_id as context_id,
            true as is_read,
            COALESCE(responded_at, created_at) as created_at,
            updated_at
        FROM messages
        WHERE response_text IS NOT NULL AND response_text != ''
    """)
    
    # Rename old table for backup
    op.rename_table('messages', 'messages_old_backup')
    
    # Rename new table to messages
    op.rename_table('messages_new', 'messages')
    
    # Update foreign key in offspring table if it exists
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name = 'offsprings_messages_fkey'
            ) THEN
                ALTER TABLE offsprings DROP CONSTRAINT offsprings_messages_fkey;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema - restore old messages table."""
    
    # Drop new messages table
    op.drop_table('messages')
    
    # Restore old messages table
    op.rename_table('messages_old_backup', 'messages')

