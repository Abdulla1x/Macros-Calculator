"""meals.created_at — when the row was written, not when the food was eaten

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-14

`meals.date` is user-chosen and freely backdated, so it cannot answer "when was
the app used". This column can. It is nullable rather than backfilled: rows
written before it existed have no record of their creation time, and copying
`date` into them would invent an observation that was never made. Readers treat
NULL as "unknown" and fall back to `date`.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Dropping this loses the logged-at times recorded since the upgrade; the
    # rows themselves survive and fall back to `date`, which is the same place
    # pre-0006 history already sits.
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.drop_column('created_at')
