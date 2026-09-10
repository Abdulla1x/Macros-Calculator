"""daily_stats, and users.last_seen_at

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10

Two changes, together because they answer one question between them: whether
anybody other than the author uses this app, and whether they come back.

daily_stats -- A NEW TABLE WITH NO user_id.

Every figure on /admin today is derived from live rows, so deleting an account
rewrites the past, and retention computed that way is survivorship-biased in
the flattering direction: it would read higher the more people quit. This table
freezes each finished day once. See the DailyStat docstring in models.py for
the cohort arithmetic and app/snapshots.py for what triggers a freeze.

⚠️ The eleven-item new-table checklist does NOT apply in full here, and the
reason is worth stating rather than leaving to look like an oversight. Nine of
those items exist because a new table holds data an ACCOUNT owns: the export
must carry it, the deletion copy must enumerate it, the isolation suite must
prove one user cannot read another's rows. **This table has no user_id.** It is
not exported (there is nothing of yours in it), it is not deleted with an
account (that is the entire point), and it cannot leak across accounts because
it does not belong to one. What does apply is item 10 -- the admin router and
Admin.tsx, because a count nobody can read is not a metric -- and item 11, the
positive privacy assertion in tests/test_admin.py.

NOT NULL with a server_default on the four counts: the table starts empty, so
there is no backfill for the ALTER to fail on, but a snapshot row that is
missing a count would be indistinguishable from a day nobody used the app. Zero
is a real, meaningful value here; NULL is not.

The two cohort columns are the opposite case and are deliberately nullable.
NULL means "this window has not closed yet", which must never be read as "zero
people came back" -- so the ratio is summed over non-NULL rows only. Same rule
as ai_analyses.provider_ms from 0015.

Unique index on date, not merely an index: the backfill is idempotent BECAUSE
the database refuses a second row for a day, and app/upsert.py turns the
resulting race into a retry rather than a 500.

users.last_seen_at -- ONE NULLABLE COLUMN.

The one signal the app never recorded. admin.py's last_active_at derives from
rows an account WROTE, so someone who opens the dashboard daily and logs
nothing looks identical to someone who never returned -- opposite problems with
opposite fixes. Written at most once per UTC day per account (auth/deps.py),
which is what makes a column affordable: the objection on record against a
last_seen column was that keeping it accurate means a write on every
authenticated request, and at date precision it does not.

Nullable with no server_default and no backfill, for the reason 0016 gives for
goal_weight_kg: NULL is the honest value for every existing account, because
this app has never observed when they last visited and inventing a timestamp
would put a measurement where there is none. The column fills itself on each
account's next request.

No batch_alter_table for the users change: nothing existing is rebuilt, only
added to.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'daily_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('signups', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_users', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('meals', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_users', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_meals', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cohort_d7_retained', sa.Integer(), nullable=True),
        sa.Column('cohort_d30_retained', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_daily_stats_date', 'daily_stats', ['date'], unique=True,
    )
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_seen_at')
    op.drop_index('ix_daily_stats_date', table_name='daily_stats')
    op.drop_table('daily_stats')
