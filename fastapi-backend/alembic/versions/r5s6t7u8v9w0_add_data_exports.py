"""add data_exports table for breeder data export jobs

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'r5s6t7u8v9w0'
down_revision: Union[str, Sequence[str], None] = 'q4r5s6t7u8v9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'data_exports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_token_hash', sa.String(length=64), nullable=True),
        sa.Column('download_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_token_used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_data_exports_user_id', 'data_exports', ['user_id'])
    op.create_index('ix_data_exports_download_token_hash', 'data_exports', ['download_token_hash'])


def downgrade() -> None:
    op.drop_index('ix_data_exports_download_token_hash', table_name='data_exports')
    op.drop_index('ix_data_exports_user_id', table_name='data_exports')
    op.drop_table('data_exports')
