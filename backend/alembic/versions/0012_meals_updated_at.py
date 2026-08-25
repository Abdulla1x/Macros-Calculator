"""meals.updated_at — when the row was last rewritten, null until it is

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-25

A companion to 0006's `created_at`, and nullable for a different reason.

0006 left `created_at` nullable because pre-0006 rows genuinely had no record
of when they were written. This column is nullable because *most rows never
get one*: a meal that has never been corrected has no edit time, and defaulting
it to `created_at` on insert would report every meal in the table as revised.
Null means "no recorded edit" -- never corrected, or corrected before this
column existed. Readers wanting "when did this row last change" coalesce
updated_at over created_at.

Nothing is backfilled, and nothing needs to be: there is no observation to
recover. Which pre-0012 rows had been edited was never recorded anywhere, so
inventing a timestamp for them would be fabricating history, the same call 0006
made.

batch_alter_table because this alters an existing table and SQLite cannot add a
column any other way; on Postgres it is a plain ADD COLUMN.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Dropping this loses the edit times recorded since the upgrade. The meals
    # themselves are untouched -- they simply go back to reporting no recorded
    # edit, which is where every pre-0012 row already sits.
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
