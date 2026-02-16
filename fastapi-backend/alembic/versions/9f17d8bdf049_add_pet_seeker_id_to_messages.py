"""add_pet_seeker_id_to_messages

Revision ID: 9f17d8bdf049
Revises: c2d3e4f5g6h7
Create Date: 2026-02-13 22:29:00.896577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9f17d8bdf049'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5g6h7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pet_seeker_id foreign key to messages table for account linking."""
    # Add nullable UUID field referencing users table
    op.add_column(
        'messages',
        sa.Column('pet_seeker_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Create foreign key constraint with ON DELETE SET NULL
    op.create_foreign_key(
        'fk_messages_pet_seeker_id',
        'messages', 'users',
        ['pet_seeker_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Create index on pet_seeker_id for efficient queries
    op.create_index('ix_messages_pet_seeker_id', 'messages', ['pet_seeker_id'])


def downgrade() -> None:
    """Remove pet_seeker_id from messages table."""
    # Drop index
    op.drop_index('ix_messages_pet_seeker_id', 'messages')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_messages_pet_seeker_id', 'messages', type_='foreignkey')
    
    # Drop column
    op.drop_column('messages', 'pet_seeker_id')
