"""rename pet_documents to documents with polymorphic entity columns

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-03-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'l9m0n1o2p3q4'
down_revision: Union[str, None] = 'k8l9m0n1o2p3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entity_type and entity_id columns
    op.add_column('pet_documents', sa.Column('entity_type', sa.String(50), nullable=True))
    op.add_column('pet_documents', sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True))

    # Populate from existing pet_id
    op.execute("UPDATE pet_documents SET entity_type = 'pet', entity_id = pet_id")

    # Make non-nullable
    op.alter_column('pet_documents', 'entity_type', nullable=False)
    op.alter_column('pet_documents', 'entity_id', nullable=False)

    # Drop old foreign key and index
    op.drop_constraint('pet_documents_pet_id_fkey', 'pet_documents', type_='foreignkey')
    op.drop_index('ix_pet_documents_pet_id', table_name='pet_documents')
    op.drop_column('pet_documents', 'pet_id')

    # Rename table
    op.rename_table('pet_documents', 'documents')

    # Add new indexes
    op.create_index('ix_documents_entity', 'documents', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('ix_documents_entity', table_name='documents')
    op.rename_table('documents', 'pet_documents')
    op.add_column('pet_documents', sa.Column('pet_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE pet_documents SET pet_id = entity_id WHERE entity_type = 'pet'")
    op.alter_column('pet_documents', 'pet_id', nullable=False)
    op.create_index('ix_pet_documents_pet_id', 'pet_documents', ['pet_id'])
    op.create_foreign_key('pet_documents_pet_id_fkey', 'pet_documents', 'pets', ['pet_id'], ['id'], ondelete='CASCADE')
    op.drop_column('pet_documents', 'entity_type')
    op.drop_column('pet_documents', 'entity_id')
