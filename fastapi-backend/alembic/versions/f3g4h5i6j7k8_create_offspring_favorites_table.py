"""create_offspring_favorites_table

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-03-03 10:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3g4h5i6j7k8'
down_revision: Union[str, Sequence[str], None] = 'e2f3g4h5i6j7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create offspring_favorites table for tracking pet seeker favorites."""
    op.create_table(
        'offspring_favorites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('offspring_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        
        # Foreign key constraints with CASCADE delete
        sa.ForeignKeyConstraint(['offspring_id'], ['offsprings.id'], name='fk_offspring_favorites_offspring_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_offspring_favorites_user_id', ondelete='CASCADE'),
        
        # Unique constraint to prevent duplicate favorites
        sa.UniqueConstraint('offspring_id', 'user_id', name='uq_offspring_favorites_offspring_user'),
    )
    
    # Create indexes
    op.create_index('ix_offspring_favorites_offspring_id', 'offspring_favorites', ['offspring_id'])
    op.create_index('ix_offspring_favorites_user_id', 'offspring_favorites', ['user_id'])


def downgrade() -> None:
    """Drop offspring_favorites table."""
    op.drop_index('ix_offspring_favorites_user_id', 'offspring_favorites')
    op.drop_index('ix_offspring_favorites_offspring_id', 'offspring_favorites')
    op.drop_table('offspring_favorites')
