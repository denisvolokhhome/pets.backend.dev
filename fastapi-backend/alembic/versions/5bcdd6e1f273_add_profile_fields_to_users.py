"""add_profile_fields_to_users

Revision ID: 5bcdd6e1f273
Revises: 62376807fc63
Create Date: 2026-01-24 22:08:17.769095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5bcdd6e1f273'
down_revision: Union[str, Sequence[str], None] = '62376807fc63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add profile fields to users table
    op.add_column('users', sa.Column('breedery_name', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('profile_image_path', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('breedery_description', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('search_tags', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove profile fields from users table
    op.drop_column('users', 'search_tags')
    op.drop_column('users', 'breedery_description')
    op.drop_column('users', 'profile_image_path')
    op.drop_column('users', 'breedery_name')
