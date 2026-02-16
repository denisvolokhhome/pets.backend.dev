"""add_user_types_and_oauth_fields

Revision ID: c2d3e4f5g6h7
Revises: b1c2d3e4f5g6
Create Date: 2026-02-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5g6h7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5g6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user type classification and OAuth support fields."""
    # Add is_breeder field with default True for backward compatibility
    op.add_column('users', sa.Column('is_breeder', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add OAuth provider fields
    op.add_column('users', sa.Column('oauth_provider', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('oauth_id', sa.String(length=255), nullable=True))
    
    # Create indexes for efficient filtering and OAuth lookups
    op.create_index('ix_users_is_breeder', 'users', ['is_breeder'])
    op.create_index('ix_users_oauth_id', 'users', ['oauth_id'])


def downgrade() -> None:
    """Remove user type classification and OAuth support fields."""
    # Drop indexes
    op.drop_index('ix_users_oauth_id', 'users')
    op.drop_index('ix_users_is_breeder', 'users')
    
    # Drop columns
    op.drop_column('users', 'oauth_id')
    op.drop_column('users', 'oauth_provider')
    op.drop_column('users', 'is_breeder')
