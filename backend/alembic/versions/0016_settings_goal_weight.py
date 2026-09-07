"""goal weight: settings.goal_weight_kg

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-07

One column on an existing table, so the six-item settings-column checklist
applies rather than the eleven-item one for a new table.

Nullable, with no server_default and no backfill. NULL means "I have not said
what I am aiming for", and unlike settings.water_goal_ml -- where NULL means
"derive it from my weight" -- there is nothing to derive a goal weight from.
That is the difference that decides the shape: water_goal_ml can be empty
because the app can answer for you, and this one is empty because only you can.

No server_default is not an oversight either. settings.targets_auto and
settings.weigh_in_reminder_days both needed one because they are NOT NULL and
the ALTER would fail outright against a table that already has rows -- which in
production is every account. A nullable column adds NULL to those rows without
being told to.

No CHECK constraint. The bound (greater than zero, at most MAX_WEIGHT_KG) is a
range rather than a short IN (...) list, and schemas.Settings is the gate for
it, exactly as schemas.WeightEntryCreate already is for the weigh-ins this
column is compared against.

No batch_alter_table: nothing existing is rebuilt, only added to.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column('goal_weight_kg', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('settings', 'goal_weight_kg')
