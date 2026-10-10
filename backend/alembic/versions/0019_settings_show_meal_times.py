"""settings.show_meal_times

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-10

One column on an existing table, so the six-item settings-column checklist
applies rather than the eleven-item one for a new table.

Whether Today's meal rows show the time each meal was logged. A plain on/off
with no third state, so NOT NULL, and therefore a server_default: without one
this ALTER fails outright on a table that already has rows, which in
production is every account. True, because the design's meal row shows the
time; anyone who finds it noise switches it off. The same pairing
settings.targets_auto uses, with the opposite default.

No batch_alter_table: nothing existing is rebuilt, only added to.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column(
            'show_meal_times',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column('settings', 'show_meal_times')
