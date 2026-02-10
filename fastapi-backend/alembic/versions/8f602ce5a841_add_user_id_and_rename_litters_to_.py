"""add_user_id_and_rename_litters_to_breedings

Revision ID: 8f602ce5a841
Revises: 26d077d96d3a
Create Date: 2026-02-08 22:30:10.030507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f602ce5a841'
down_revision: Union[str, Sequence[str], None] = '26d077d96d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add user_id column to litters table
    op.add_column('litters', sa.Column('user_id', sa.UUID(), nullable=True))
    
    # Step 2: Populate user_id from pets table (get user_id from parent pets)
    # This query finds the user_id from the first parent pet assigned to each litter
    op.execute("""
        UPDATE litters 
        SET user_id = (
            SELECT DISTINCT p.user_id 
            FROM litter_pets lp
            JOIN pets p ON p.id = lp.pet_id
            WHERE lp.litter_id = litters.id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM litter_pets WHERE litter_id = litters.id
        )
    """)
    
    # Step 3: Make user_id NOT NULL after populating data
    op.alter_column('litters', 'user_id', nullable=False)
    
    # Step 4: Add foreign key constraint
    op.create_foreign_key(
        'fk_litters_user_id',
        'litters', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Step 5: Create index on user_id
    op.create_index('ix_litters_user_id', 'litters', ['user_id'])
    
    # Step 6: Rename litters table to breedings
    op.rename_table('litters', 'breedings')
    
    # Step 7: Rename litter_pets table to breeding_pets
    op.rename_table('litter_pets', 'breeding_pets')
    
    # Step 8: Update foreign key references in pets table
    # Drop old foreign key
    op.drop_constraint('pets_litter_id_fkey', 'pets', type_='foreignkey')
    
    # Rename column in pets table
    op.alter_column('pets', 'litter_id', new_column_name='breeding_id')
    
    # Recreate foreign key with new name
    op.create_foreign_key(
        'fk_pets_breeding_id',
        'pets', 'breedings',
        ['breeding_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Step 9: Update foreign key in breeding_pets table
    # Drop old foreign key
    op.drop_constraint('litter_pets_litter_id_fkey', 'breeding_pets', type_='foreignkey')
    
    # Rename column
    op.alter_column('breeding_pets', 'litter_id', new_column_name='breeding_id')
    
    # Recreate foreign key
    op.create_foreign_key(
        'fk_breeding_pets_breeding_id',
        'breeding_pets', 'breedings',
        ['breeding_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Step 10: Update indexes
    op.drop_index('ix_pets_litter_id', 'pets')
    op.create_index('ix_pets_breeding_id', 'pets', ['breeding_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse all operations in opposite order
    
    # Step 1: Revert index changes
    op.drop_index('ix_pets_breeding_id', 'pets')
    op.create_index('ix_pets_litter_id', 'pets', ['litter_id'])
    
    # Step 2: Revert breeding_pets foreign key
    op.drop_constraint('fk_breeding_pets_breeding_id', 'breeding_pets', type_='foreignkey')
    op.alter_column('breeding_pets', 'breeding_id', new_column_name='litter_id')
    op.create_foreign_key(
        'litter_pets_litter_id_fkey',
        'breeding_pets', 'breedings',
        ['litter_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Step 3: Revert pets foreign key
    op.drop_constraint('fk_pets_breeding_id', 'pets', type_='foreignkey')
    op.alter_column('pets', 'breeding_id', new_column_name='litter_id')
    op.create_foreign_key(
        'pets_litter_id_fkey',
        'pets', 'breedings',
        ['litter_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Step 4: Rename tables back
    op.rename_table('breeding_pets', 'litter_pets')
    op.rename_table('breedings', 'litters')
    
    # Step 5: Remove user_id column and related constraints
    op.drop_index('ix_litters_user_id', 'litters')
    op.drop_constraint('fk_litters_user_id', 'litters', type_='foreignkey')
    op.drop_column('litters', 'user_id')
