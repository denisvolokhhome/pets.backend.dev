"""add breeder_reviews table

Revision ID: 383e3fcc6d06
Revises: 7b0e8a7f617e
Create Date: 2026-04-04 11:30:41.009540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '383e3fcc6d06'
down_revision: Union[str, Sequence[str], None] = '7b0e8a7f617e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('breeder_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reviewer_id', sa.UUID(), nullable=False),
        sa.Column('breeder_id', sa.UUID(), nullable=False),
        sa.Column('thread_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('tags', sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_review_rating_range'),
        sa.ForeignKeyConstraint(['breeder_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reviewer_id', 'breeder_id', 'thread_id', name='uq_review_per_thread'),
    )
    op.create_index(op.f('ix_breeder_reviews_breeder_id'), 'breeder_reviews', ['breeder_id'], unique=False)
    op.create_index(op.f('ix_breeder_reviews_reviewer_id'), 'breeder_reviews', ['reviewer_id'], unique=False)
    op.create_index(op.f('ix_breeder_reviews_thread_id'), 'breeder_reviews', ['thread_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_breeder_reviews_thread_id'), table_name='breeder_reviews')
    op.drop_index(op.f('ix_breeder_reviews_reviewer_id'), table_name='breeder_reviews')
    op.drop_index(op.f('ix_breeder_reviews_breeder_id'), table_name='breeder_reviews')
    op.drop_table('breeder_reviews')
