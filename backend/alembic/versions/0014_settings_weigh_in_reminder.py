"""weigh-in reminder: settings.weigh_in_reminder_time + _days

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-27

Two columns on an existing table and no new table, so the eleven-item checklist
does not apply -- the six-item settings-column one does.

The two columns are deliberately not the same shape, and the asymmetry is the
design rather than an oversight:

* `weigh_in_reminder_time` is NULLABLE, and NULL means the reminder is OFF.
  The opt-in and the time are one column for the reason water_goal_ml gives in
  models.py -- NULL already carries the flag, and a value plus a separate
  boolean is two columns that can disagree. Nullable, so no backfill and no
  server_default: every existing account starts with the reminder off, which is
  the only safe default for a feature nobody has opted into.

* `weigh_in_reminder_days` is NOT NULL with server_default '1'. It cannot
  express "off", so it cannot contradict the column that can. The
  server_default is not decoration: without it this ALTER fails outright on any
  table that already has rows, which in production is every account. It is the
  same pairing settings.targets_auto uses.

No CHECK constraint on the time, unlike settings.sex / activity_level /
weight_unit beside it. Those are short IN (...) lists, which SQLite and
Postgres spell identically; an "HH:MM" pattern is a regex and they do not
(GLOB vs ~). schemas.ClockTime is the gate, exactly as it already is for the
supplement times this format is borrowed from.

No batch_alter_table: nothing existing is rebuilt, only added to.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column('weigh_in_reminder_time', sa.String(length=5), nullable=True),
    )
    op.add_column(
        'settings',
        sa.Column(
            'weigh_in_reminder_days',
            sa.Integer(),
            nullable=False,
            server_default='1',
        ),
    )


def downgrade() -> None:
    op.drop_column('settings', 'weigh_in_reminder_days')
    op.drop_column('settings', 'weigh_in_reminder_time')
