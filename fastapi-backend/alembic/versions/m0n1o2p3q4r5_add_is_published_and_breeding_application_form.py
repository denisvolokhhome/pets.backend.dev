"""add is_published to offsprings and breeding_application_forms table

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'm0n1o2p3q4r5'
down_revision: Union[str, None] = 'l9m0n1o2p3q4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_published column to offsprings (default False — unpublished)
    op.add_column(
        'offsprings',
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_index('ix_offsprings_is_published', 'offsprings', ['is_published'])

    # Create breeding_application_forms table
    op.create_table(
        'breeding_application_forms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('breeding_id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('form_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['breeding_id'], ['breedings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('breeding_id'),
    )
    op.create_index('ix_breeding_application_forms_breeding_id', 'breeding_application_forms', ['breeding_id'])
    op.create_index('ix_breeding_application_forms_user_id', 'breeding_application_forms', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_breeding_application_forms_user_id', table_name='breeding_application_forms')
    op.drop_index('ix_breeding_application_forms_breeding_id', table_name='breeding_application_forms')
    op.drop_table('breeding_application_forms')

    op.drop_index('ix_offsprings_is_published', table_name='offsprings')
    op.drop_column('offsprings', 'is_published')
