"""
Atomic puppy reservation shared by every flow that gives a puppy to a family
(litter applications and the waitlist).

A single conditional UPDATE ... WHERE status = 'Available' AND <no holder> is the
lock: when two requests race, Postgres makes the second wait for the first's row
lock, re-checks the WHERE clause after the first commits, and updates nothing.

"Holder" is checked explicitly (an assigned litter application or a matched
waitlist entry) rather than trusting the puppy's status alone, because a breeder
can edit a puppy's status by hand. So a puppy can't be given to a second family,
and undoing one family's assignment never frees a puppy someone else now holds.
"""
import uuid
from typing import Optional

from sqlalchemy import and_, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.litter_application import LitterApplication
from app.models.offspring import Offspring
from app.models.waitlist_entry import WaitlistEntry

AVAILABLE = "Available"
RESERVED = "Reserved"


def _held_by_someone(*, except_application: Optional[uuid.UUID] = None,
                     except_waitlist_entry: Optional[uuid.UUID] = None):
    """SQL condition: some family (other than the given holder) currently holds the puppy."""
    app_cond = [LitterApplication.assigned_offspring_id == Offspring.id,
                LitterApplication.status == "assigned"]
    if except_application is not None:
        app_cond.append(LitterApplication.id != except_application)
    entry_cond = [WaitlistEntry.offspring_id == Offspring.id, WaitlistEntry.status == "matched"]
    if except_waitlist_entry is not None:
        entry_cond.append(WaitlistEntry.id != except_waitlist_entry)
    return exists(select(LitterApplication.id).where(and_(*app_cond))) | exists(
        select(WaitlistEntry.id).where(and_(*entry_cond)))


async def reserve_offspring(db: AsyncSession, *, offspring_id: uuid.UUID, breeding_id: int,
                            breeder_id: uuid.UUID) -> bool:
    """Move an Available, unheld puppy of this breeder's litter to Reserved. False if it can't be."""
    result = await db.execute(
        update(Offspring)
        .where(
            Offspring.id == offspring_id,
            Offspring.breeding_id == breeding_id,
            Offspring.user_id == breeder_id,
            Offspring.status == AVAILABLE,
            ~_held_by_someone(),
        )
        .values(status=RESERVED)
        .returning(Offspring.id)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none() is not None


async def release_offspring(db: AsyncSession, *, offspring_id: uuid.UUID, breeder_id: uuid.UUID,
                            releasing_application: Optional[uuid.UUID] = None,
                            releasing_waitlist_entry: Optional[uuid.UUID] = None) -> None:
    """
    Return a Reserved puppy to Available, unless another family holds it now
    (or the breeder already marked it Sold etc.).
    """
    await db.execute(
        update(Offspring)
        .where(
            Offspring.id == offspring_id,
            Offspring.user_id == breeder_id,
            Offspring.status == RESERVED,
            ~_held_by_someone(except_application=releasing_application,
                              except_waitlist_entry=releasing_waitlist_entry),
        )
        .values(status=AVAILABLE)
        .execution_options(synchronize_session=False)
    )
