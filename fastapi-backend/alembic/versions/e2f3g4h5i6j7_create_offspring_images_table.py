"""create_offspring_images_table

Revision ID: e2f3g4h5i6j7
Revises: d1e2f3g4h5i6
Create Date: 2026-03-03 10:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e2f3g4h5i6j7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3g4h5i6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create offspring_images table for managing multiple images per offspring."""
    op.create_table(
        'offspring_images',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('offspring_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('image_path', sa.String(500), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        
        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(['offspring_id'], ['offsprings.id'], name='fk_offspring_images_offspring_id', ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index('ix_offspring_images_offspring_id', 'offspring_images', ['offspring_id'])
    op.create_index('ix_offspring_images_display_order', 'offspring_images', ['display_order'])
    
    # Create unique partial index to ensure only one primary image per offspring
    op.create_index(
        'ix_offspring_images_unique_primary',
        'offspring_images',
        ['offspring_id'],
        unique=True,
        postgresql_where=sa.text('is_primary = true')
    )


def downgrade() -> None:
    """Drop offspring_images table."""
    op.drop_index('ix_offspring_images_unique_primary', 'offspring_images')
    op.drop_index('ix_offspring_images_display_order', 'offspring_images')
    op.drop_index('ix_offspring_images_offspring_id', 'offspring_images')
    op.drop_table('offspring_images')
