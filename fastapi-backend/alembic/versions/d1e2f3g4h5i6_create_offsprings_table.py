"""create_offsprings_table

Revision ID: d1e2f3g4h5i6
Revises: 9f17d8bdf049
Create Date: 2026-03-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3g4h5i6'
down_revision: Union[str, Sequence[str], None] = '9f17d8bdf049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create offsprings table for tracking individual offspring from breedings."""
    op.create_table(
        'offsprings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('breeding_id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('breed_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('gender', sa.String(50), nullable=False),
        sa.Column('date_of_birth', sa.Date(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='Available'),
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color_markings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        
        # Foreign key constraints
        sa.ForeignKeyConstraint(['breeding_id'], ['breedings.id'], name='fk_offsprings_breeding_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_offsprings_user_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['breed_id'], ['breeds.id'], name='fk_offsprings_breed_id', ondelete='SET NULL'),
        
        # Check constraints
        sa.CheckConstraint("gender IN ('Male', 'Female')", name='ck_offsprings_gender'),
        sa.CheckConstraint("status IN ('Available', 'Reserved', 'Sold', 'Archived')", name='ck_offsprings_status'),
        sa.CheckConstraint('date_of_birth <= CURRENT_DATE', name='ck_offsprings_date_of_birth'),
        sa.CheckConstraint('price >= 0', name='ck_offsprings_price'),
    )
    
    # Create indexes
    op.create_index('ix_offsprings_breeding_id', 'offsprings', ['breeding_id'])
    op.create_index('ix_offsprings_user_id', 'offsprings', ['user_id'])
    op.create_index('ix_offsprings_breed_id', 'offsprings', ['breed_id'])
    op.create_index('ix_offsprings_status', 'offsprings', ['status'])
    op.create_index('ix_offsprings_date_of_birth', 'offsprings', ['date_of_birth'])


def downgrade() -> None:
    """Drop offsprings table."""
    op.drop_index('ix_offsprings_date_of_birth', 'offsprings')
    op.drop_index('ix_offsprings_status', 'offsprings')
    op.drop_index('ix_offsprings_breed_id', 'offsprings')
    op.drop_index('ix_offsprings_user_id', 'offsprings')
    op.drop_index('ix_offsprings_breeding_id', 'offsprings')
    op.drop_table('offsprings')
