"""backfill_pet_seeker_account_type

Revision ID: 23cb5dfcc878
Revises: p3q4r5s6t7u8
Create Date: 2026-09-13 14:03:46.402069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23cb5dfcc878'
down_revision: Union[str, Sequence[str], None] = 'p3q4r5s6t7u8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill account_type for accounts stuck at the 'breeder' default.

    Registration paths that create non-breeder users (pet-seeker
    registration, guest-to-account conversion, Google OAuth signup) set
    is_breeder=False but historically never set account_type, so those rows
    silently kept the column's server_default of 'breeder'. That mismatch
    (is_breeder=False, account_type='breeder') hides the frontend's
    "Convert to Breeder" option, since it requires account_type=='pet_seeker'.
    The one-time backfill in p3q4r5s6t7u8 only covered rows that existed at
    that migration's run time; this repeats it for every row still affected.
    """
    op.execute(
        "UPDATE users SET account_type = 'pet_seeker' "
        "WHERE is_breeder = false AND account_type = 'breeder'"
    )


def downgrade() -> None:
    """No-op: reverting a data backfill would re-introduce the bug."""
    pass
