"""steps tracker: steps table + settings.steps_goal

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-21

The index here IS unique on (user_id, date), which is the opposite of 0009's
and the one thing about this schema easiest to "tidy up" into a bug. Water is
event rows, so several a day is the point; a step count is one figure per day
that gets corrected, so POST /api/steps upserts on this pair and the constraint
is what makes re-logging a date a correction rather than a second day.

`created_at` is NOT NULL here, unlike water_logs' but like weights'. The model
supplies it with a Python-side default on every insert, and the table is new,
so there is no pre-existing row to leave without one.

The settings column is nullable, so there is no backfill and no server_default.
Note it does not mean what its neighbour means: water_goal_ml NULL says "derive
it from my weight", steps_goal NULL says "I have no goal".

No batch_alter_table anywhere -- nothing existing is being rebuilt.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('steps', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Unique: one row per user per day, upserted.
    op.create_index(
        'uq_steps_user_date', 'steps', ['user_id', 'date'], unique=True
    )

    op.add_column('settings', sa.Column('steps_goal', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('settings', 'steps_goal')
    op.drop_index('uq_steps_user_date', table_name='steps')
    op.drop_table('steps')
