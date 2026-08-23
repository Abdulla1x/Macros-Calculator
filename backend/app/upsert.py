"""Upsert against a unique index, including the race the SELECT cannot close.

Four endpoints upsert by looking the row up, creating it if it is missing, and
committing. That is correct until the same account sends two of them at once --
from a double-tapped button, a retried request, or two open tabs -- and both
SELECTs miss. Then both INSERT, the unique index refuses the second, and the
loser's commit raises IntegrityError out of the handler as a 500.

`routers/supplements.py` already states the rule this module implements:

    The expression index, not a pre-flight SELECT: a check-then-insert has a
    race a unique constraint does not, and this is the same shape signup uses
    for a duplicate email.

Supplements answers 409, because creating a supplement is create-only and the
second caller genuinely asked for something that cannot happen. These four are
different: they are upserts by design. `save_food` documents "updates macros if
the name exists", and weights and steps upsert by date. The second caller asked
for "make it so", and it can be so -- the row they wanted now exists. Answering
409 would invent a failure for a request that should simply succeed.

So the loser re-reads and applies its update on top, which is what it would have
done had the two arrived a millisecond apart. Last writer wins, exactly as it
does today for two sequential saves.

`build` re-runs the whole find-or-create-and-apply, rather than the caller
holding a row across the retry, because `rollback()` detaches everything the
first attempt touched -- including any related write in the same transaction.
Redoing it is the only way the second attempt is a genuine second attempt and
not a half-rolled-back first one.

Not ON CONFLICT: the syntax is dialect-specific, and this runs on SQLite in
development and Postgres in production. The routers already say so.
"""
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

Row = TypeVar("Row")


def upsert(db: Session, build: Callable[[], Row]) -> Row:
    """Run `build`, commit, and redo both once if a concurrent insert won.

    `build` must find-or-create the row, apply the caller's values, and return
    it -- and it must be safe to call twice, because on the retry it will be.
    Only one retry: the second attempt's SELECT runs after the winner committed,
    so it finds the row and takes the UPDATE path, which cannot collide again.
    A loop here would be a loop that can only ever run once.
    """
    row = build()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = build()
        db.commit()
    return row
