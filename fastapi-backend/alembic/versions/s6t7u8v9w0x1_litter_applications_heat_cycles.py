"""litter applications, heat cycles and breeder reminders

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 's6t7u8v9w0x1'
down_revision: Union[str, Sequence[str], None] = 'r5s6t7u8v9w0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        'notification_preferences',
        sa.Column('application_update', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.add_column(
        'breeding_application_forms',
        sa.Column('accepting_litter_applications', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
    )

    op.create_table(
        'litter_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('breeding_id', sa.Integer(), sa.ForeignKey('breedings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('breeder_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('applicant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('applicant_name', sa.String(length=255), nullable=True),
        sa.Column('applicant_email', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('requested_offspring_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('offsprings.id', ondelete='SET NULL'), nullable=True),
        sa.Column('answers', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='new'),
        sa.Column('assigned_offspring_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('offsprings.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index('ix_litter_applications_breeding_id', 'litter_applications', ['breeding_id'])
    op.create_index('ix_litter_applications_breeder_id', 'litter_applications', ['breeder_id'])
    op.create_index('ix_litter_applications_applicant_id', 'litter_applications', ['applicant_id'])
    op.create_index('ix_litter_applications_assigned_offspring_id', 'litter_applications',
                    ['assigned_offspring_id'])
    op.create_index('uq_litter_applications_assigned_offspring', 'litter_applications',
                    ['assigned_offspring_id'], unique=True,
                    postgresql_where=sa.text("status = 'assigned'"))
    op.create_index('uq_litter_applications_open_per_applicant', 'litter_applications',
                    ['breeding_id', 'applicant_id', 'source',
                     sa.text("coalesce(requested_offspring_id, '00000000-0000-0000-0000-000000000000'::uuid)")],
                    unique=True,
                    postgresql_where=sa.text("status <> 'declined' AND applicant_id IS NOT NULL"))

    op.create_table(
        'heat_cycles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('pet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint('end_date IS NULL OR end_date >= start_date', name='ck_heat_cycles_end_after_start'),
    )
    op.create_index('ix_heat_cycles_pet_id', 'heat_cycles', ['pet_id'])
    op.create_index('ix_heat_cycles_user_id', 'heat_cycles', ['user_id'])
    op.create_index('uq_heat_cycles_one_open_per_pet', 'heat_cycles', ['pet_id'], unique=True,
                    postgresql_where=sa.text('end_date IS NULL'))

    op.create_table(
        'breeder_reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('pet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('remind_on', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index('ix_breeder_reminders_pet_id', 'breeder_reminders', ['pet_id'])
    op.create_index('ix_breeder_reminders_user_id', 'breeder_reminders', ['user_id'])
    op.create_index('ix_breeder_reminders_remind_on', 'breeder_reminders', ['remind_on'])


def downgrade() -> None:
    op.drop_table('breeder_reminders')
    op.drop_table('heat_cycles')
    op.drop_table('litter_applications')
    op.drop_column('breeding_application_forms', 'accepting_litter_applications')
    op.drop_column('notification_preferences', 'application_update')
