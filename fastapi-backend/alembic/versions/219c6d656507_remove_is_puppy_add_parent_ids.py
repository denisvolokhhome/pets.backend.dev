"""remove_is_puppy_add_parent_ids

Revision ID: 219c6d656507
Revises: bec93c200a00
Create Date: 2026-03-05 18:53:10.171511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '219c6d656507'
down_revision: Union[str, Sequence[str], None] = 'bec93c200a00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove is_puppy column from pets table
    op.drop_column('pets', 'is_puppy')
    
    # Add father_id and mother_id columns to offsprings table
    op.add_column('offsprings', sa.Column('father_id', sa.UUID(), nullable=True))
    op.add_column('offsprings', sa.Column('mother_id', sa.UUID(), nullable=True))
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_offsprings_father_id',
        'offsprings', 'pets',
        ['father_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_offsprings_mother_id',
        'offsprings', 'pets',
        ['mother_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove foreign key constraints
    op.drop_constraint('fk_offsprings_mother_id', 'offsprings', type_='foreignkey')
    op.drop_constraint('fk_offsprings_father_id', 'offsprings', type_='foreignkey')
    
    # Remove father_id and mother_id columns from offsprings table
    op.drop_column('offsprings', 'mother_id')
    op.drop_column('offsprings', 'father_id')
    
    # Add back is_puppy column to pets table
    op.add_column('pets', sa.Column('is_puppy', sa.Boolean(), nullable=True))
