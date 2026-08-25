"""calorie banking: calorie_plan_days

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-25

One table and no settings column, for the reason 0011 gives: an adjustment
belongs to a day, not to the account, so there is nothing to hang off the
settings row and nothing to backfill on it.

The unique index is the one to not "simplify". It spans (user_id, date) rather
than including event_date, and that narrower span is the point: a day may be
moved by at most one plan, ever. Widening it to admit event_date would let two
plans stack deltas on the same Tuesday, and cancelling either would then be
ambiguous about which delta to withdraw. Overlap is refused at write time and
names the plan that owns the day.

`kind` is CHECK-constrained the way settings.sex is. It is derivable from
whether the group has a row on its own event_date, and is stored anyway: the
two kinds satisfy different sum rules that are only checkable at write time, so
a reader that had to infer it would be re-deriving a fact nobody could verify.

Calorie deltas are Float rather than Integer even though they are always whole
kcal. Every other calorie in this schema is Float -- meals, the four goal
columns -- and a single Integer among them would make joins and comparisons
quietly type-mixed for no gain.

No batch_alter_table: nothing existing is rebuilt.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'calorie_plan_days',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('calorie_delta', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('planned', 'compensating')",
            name='ck_calorie_plan_days_kind',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Unique: one adjustment per day, which is what makes a plan cancellable as
    # a unit rather than a set of deltas nobody can attribute.
    op.create_index(
        'uq_calorie_plan_days_user_date', 'calorie_plan_days',
        ['user_id', 'date'], unique=True,
    )


def downgrade() -> None:
    # Dropping this discards every plan. Nothing else moves: the four goal
    # columns on `settings` were never touched by this feature, so every day
    # simply goes back to being drawn against the stored goal, which is where
    # an unplanned day already sits.
    op.drop_index('uq_calorie_plan_days_user_date', table_name='calorie_plan_days')
    op.drop_table('calorie_plan_days')
