"""mobile sign-in QR codes (instant mobile switch)

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 't7u8v9w0x1y2'
down_revision: Union[str, Sequence[str], None] = 's6t7u8v9w0x1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mobile_signin_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('target_path', sa.String(length=500), nullable=False, server_default='/dashboard'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_ip_hash', sa.String(length=64), nullable=True),
        sa.Column('used_user_agent', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_mobile_signin_tokens_user_id', 'mobile_signin_tokens', ['user_id'])
    op.create_index('ix_mobile_signin_tokens_token_hash', 'mobile_signin_tokens', ['token_hash'], unique=True)
    op.create_index('ix_mobile_signin_tokens_created_at', 'mobile_signin_tokens', ['created_at'])


def downgrade() -> None:
    op.drop_table('mobile_signin_tokens')
