"""add_status_and_litter_pets_table

Revision ID: 26a96605f43d
Revises: 5bcdd6e1f273
Create Date: 2026-01-25 16:49:04.950712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26a96605f43d'
down_revision: Union[str, Sequence[str], None] = '5bcdd6e1f273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add status column to litters table
    op.add_column('litters', sa.Column('status', sa.String(length=50), nullable=False, server_default='Started'))
    
    # Create litter_pets junction table for parent pet assignments
    op.create_table('litter_pets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('litter_id', sa.Integer(), nullable=False),
        sa.Column('pet_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['litter_id'], ['litters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pet_id'], ['pets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for the junction table
    op.create_index(op.f('ix_litter_pets_litter_id'), 'litter_pets', ['litter_id'], unique=False)
    op.create_index(op.f('ix_litter_pets_pet_id'), 'litter_pets', ['pet_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f('ix_litter_pets_pet_id'), table_name='litter_pets', if_exists=True)
    op.drop_index(op.f('ix_litter_pets_litter_id'), table_name='litter_pets', if_exists=True)
    
    # Drop litter_pets table
    op.drop_table('litter_pets', if_exists=True)
    
    # Drop status column from litters table
    op.drop_column('litters', 'status')
