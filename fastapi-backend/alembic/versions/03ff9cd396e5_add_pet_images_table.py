"""add pet_images table for multiple images support

Revision ID: 03ff9cd396e5
Revises: 02ee8bc295d4
Create Date: 2024-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '03ff9cd396e5'
down_revision: Union[str, None] = '02ee8bc295d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create pet_images table
    op.create_table(
        'pet_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pet_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('image_path', sa.String(length=500), nullable=False),
        sa.Column('image_file_name', sa.String(length=255), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['pet_id'], ['pets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pet_images_pet_id', 'pet_images', ['pet_id'])
    op.create_index('ix_pet_images_is_primary', 'pet_images', ['is_primary'])
    
    # Migrate existing pet images to new table
    op.execute("""
        INSERT INTO pet_images (pet_id, image_path, image_file_name, display_order, is_primary, created_at)
        SELECT id, image_path, image_file_name, 0, true, created_at
        FROM pets
        WHERE image_path IS NOT NULL AND image_file_name IS NOT NULL
    """)


def downgrade() -> None:
    # Drop pet_images table
    op.drop_index('ix_pet_images_is_primary', table_name='pet_images')
    op.drop_index('ix_pet_images_pet_id', table_name='pet_images')
    op.drop_table('pet_images')
